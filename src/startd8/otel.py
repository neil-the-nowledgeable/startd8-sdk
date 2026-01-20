"""
OpenTelemetry configuration with ContextCore project context support.

This module provides helpers for configuring OTel resources with
ContextCore project metadata at the resource level, ensuring all
telemetry (traces, metrics, logs) includes project context.

Semantic Conventions (ContextCore):
    - io.contextcore.project.id
    - io.contextcore.project.name  
    - io.contextcore.task.id
    - io.contextcore.sprint.id
    - io.contextcore.business.criticality

Standard OTel Semantic Conventions:
    - service.name
    - service.version
    - service.namespace
    - deployment.environment
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# Conditional OTel imports
try:
    from opentelemetry import trace, metrics
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    metrics = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None
    MeterProvider = None
    PeriodicExportingMetricReader = None
    OTLPSpanExporter = None
    OTLPMetricExporter = None
    SERVICE_NAME = "service.name"
    SERVICE_VERSION = "service.version"


# ContextCore semantic convention attribute names
CONTEXTCORE_PROJECT_ID = "io.contextcore.project.id"
CONTEXTCORE_PROJECT_NAME = "io.contextcore.project.name"
CONTEXTCORE_TASK_ID = "io.contextcore.task.id"
CONTEXTCORE_SPRINT_ID = "io.contextcore.sprint.id"
CONTEXTCORE_BUSINESS_CRITICALITY = "io.contextcore.business.criticality"


@dataclass
class ProjectContext:
    """
    ContextCore project context for OTel resource attributes.
    
    All fields are optional. Non-None fields will be included
    as resource attributes on all telemetry.
    """
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    task_id: Optional[str] = None
    sprint_id: Optional[str] = None
    business_criticality: Optional[str] = None
    
    def to_resource_attributes(self) -> Dict[str, str]:
        """
        Convert to OTel resource attribute dict.
        
        Only includes non-None values.
        """
        attrs = {}
        if self.project_id:
            attrs[CONTEXTCORE_PROJECT_ID] = self.project_id
        if self.project_name:
            attrs[CONTEXTCORE_PROJECT_NAME] = self.project_name
        if self.task_id:
            attrs[CONTEXTCORE_TASK_ID] = self.task_id
        if self.sprint_id:
            attrs[CONTEXTCORE_SPRINT_ID] = self.sprint_id
        if self.business_criticality:
            attrs[CONTEXTCORE_BUSINESS_CRITICALITY] = self.business_criticality
        return attrs
    
    def is_empty(self) -> bool:
        """Check if all fields are None."""
        return all(v is None for v in [
            self.project_id, self.project_name, self.task_id, 
            self.sprint_id, self.business_criticality
        ])


@dataclass
class OTelConfig:
    """
    OpenTelemetry configuration with ContextCore support.
    
    Combines standard OTel service attributes with ContextCore
    project context for unified observability.
    """
    # Standard service attributes
    service_name: str = "startd8-sdk"
    service_version: str = "0.4.0"
    service_namespace: Optional[str] = None
    deployment_environment: str = field(
        default_factory=lambda: os.getenv("ENV", "development")
    )
    
    # ContextCore project context
    project_context: Optional[ProjectContext] = None
    
    # OTLP exporter settings
    otlp_endpoint: str = "http://localhost:4317"
    otlp_protocol: str = "grpc"  # grpc or http
    otlp_headers: Dict[str, str] = field(default_factory=dict)
    
    # Feature flags
    enable_traces: bool = True
    enable_metrics: bool = True
    
    # Export settings
    trace_batch_size: int = 512
    metrics_export_interval_ms: int = 60000  # 1 minute


def create_resource(
    service_name: str = "startd8-sdk",
    service_version: str = "0.4.0",
    deployment_environment: Optional[str] = None,
    project_context: Optional[ProjectContext] = None,
    extra_attributes: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    Create an OTel Resource with ContextCore project attributes.
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        deployment_environment: Environment (dev, staging, prod)
        project_context: ContextCore project metadata
        extra_attributes: Additional custom attributes
        
    Returns:
        OpenTelemetry Resource object, or None if OTel not available
        
    Example:
        resource = create_resource(
            service_name="my-agent",
            project_context=ProjectContext(
                project_id="startd8-sdk",
                task_id="SDK-102",
                sprint_id="sprint-1",
            )
        )
    """
    if not OTEL_AVAILABLE:
        return None
    
    # Start with standard attributes
    attributes = {
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": deployment_environment or os.getenv("ENV", "development"),
    }
    
    # Add ContextCore project attributes
    if project_context:
        attributes.update(project_context.to_resource_attributes())
    
    # Add any extra custom attributes
    if extra_attributes:
        attributes.update(extra_attributes)
    
    return Resource.create(attributes)


def configure_tracing(
    config: OTelConfig,
) -> Optional[Any]:
    """
    Configure OTel tracing with ContextCore resource attributes.
    
    Args:
        config: OTelConfig with service and project context
        
    Returns:
        Tracer instance, or None if OTel not available or disabled
    """
    if not OTEL_AVAILABLE or not config.enable_traces:
        return None
    
    resource = create_resource(
        service_name=config.service_name,
        service_version=config.service_version,
        deployment_environment=config.deployment_environment,
        project_context=config.project_context,
    )
    
    provider = TracerProvider(resource=resource)
    
    exporter = OTLPSpanExporter(
        endpoint=config.otlp_endpoint,
        headers=config.otlp_headers or None,
    )
    
    processor = BatchSpanProcessor(
        exporter,
        max_export_batch_size=config.trace_batch_size,
    )
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)
    return trace.get_tracer(config.service_name)


def configure_metrics(
    config: OTelConfig,
) -> Optional[Any]:
    """
    Configure OTel metrics with ContextCore resource attributes.
    
    Args:
        config: OTelConfig with service and project context
        
    Returns:
        Meter instance, or None if OTel not available or disabled
    """
    if not OTEL_AVAILABLE or not config.enable_metrics:
        return None
    
    resource = create_resource(
        service_name=config.service_name,
        service_version=config.service_version,
        deployment_environment=config.deployment_environment,
        project_context=config.project_context,
    )
    
    exporter = OTLPMetricExporter(
        endpoint=config.otlp_endpoint,
        headers=config.otlp_headers or None,
    )
    
    reader = PeriodicExportingMetricReader(
        exporter,
        export_interval_millis=config.metrics_export_interval_ms,
    )
    
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)
    
    return metrics.get_meter(config.service_name)


def configure_otel(
    config: OTelConfig,
) -> Dict[str, Any]:
    """
    Configure both tracing and metrics with ContextCore support.
    
    Args:
        config: OTelConfig with full configuration
        
    Returns:
        Dict with 'tracer' and 'meter' keys (values may be None)
        
    Example:
        from startd8.otel import OTelConfig, ProjectContext, configure_otel
        
        config = OTelConfig(
            service_name="my-workflow",
            project_context=ProjectContext(
                project_id="startd8-sdk",
                task_id="SDK-102",
            ),
            otlp_endpoint="http://otel-collector:4317",
        )
        
        otel = configure_otel(config)
        tracer = otel['tracer']
        meter = otel['meter']
    """
    return {
        "tracer": configure_tracing(config),
        "meter": configure_metrics(config),
        "resource_attributes": (
            config.project_context.to_resource_attributes() 
            if config.project_context else {}
        ),
    }


def add_project_context_to_span(
    span: Any,
    project_context: ProjectContext,
) -> None:
    """
    Add ContextCore attributes to an existing span.
    
    Use this to add project context to spans that were created
    before the context was known.
    
    Args:
        span: Active OTel span
        project_context: ContextCore project metadata
    """
    if span is None or project_context is None:
        return
    
    if project_context.project_id:
        span.set_attribute(CONTEXTCORE_PROJECT_ID, project_context.project_id)
    if project_context.project_name:
        span.set_attribute(CONTEXTCORE_PROJECT_NAME, project_context.project_name)
    if project_context.task_id:
        span.set_attribute(CONTEXTCORE_TASK_ID, project_context.task_id)
    if project_context.sprint_id:
        span.set_attribute(CONTEXTCORE_SPRINT_ID, project_context.sprint_id)
    if project_context.business_criticality:
        span.set_attribute(CONTEXTCORE_BUSINESS_CRITICALITY, project_context.business_criticality)


# Re-export for convenience
__all__ = [
    # Constants
    "OTEL_AVAILABLE",
    "CONTEXTCORE_PROJECT_ID",
    "CONTEXTCORE_PROJECT_NAME", 
    "CONTEXTCORE_TASK_ID",
    "CONTEXTCORE_SPRINT_ID",
    "CONTEXTCORE_BUSINESS_CRITICALITY",
    # Classes
    "ProjectContext",
    "OTelConfig",
    # Functions
    "create_resource",
    "configure_tracing",
    "configure_metrics",
    "configure_otel",
    "add_project_context_to_span",
]
