# Error Handling and Observability Review
## OpenTelemetry Integration Plan with Loki Logging Backend

**Date:** 2025-01-XX  
**Status:** Review & Recommendations  
**Priority:** High - Production Readiness  
**Backend Stack:** Grafana (Loki for Logs, Tempo for Traces, Prometheus for Metrics)  
**Grafana Instance:** http://localhost:3000 (already running)

---

## Executive Summary

This document reviews the current error handling and logging implementation in the startd8 SDK, identifies gaps, and provides a systematic plan for integrating OpenTelemetry (OTel) for comprehensive observability with **Grafana Loki** as the logging backend, **Tempo** for distributed tracing, and **Prometheus** for metrics collection.

**Note:** You already have a Grafana stack running locally at http://localhost:3000. This plan will integrate with your existing infrastructure.

### Current State: ✅ Good Foundation, ⚠️ Needs Enhancement

**Strengths:**
- ✅ Custom exception hierarchy (`exceptions.py`)
- ✅ Structured JSON logging (`logging_config.py`)
- ✅ Correlation ID support
- ✅ Some exception context preservation (`raise ... from e`)
- ✅ Error decorators (`handle_storage_errors`)

**Gaps:**
- ⚠️ Inconsistent error handling patterns across modules
- ⚠️ No distributed tracing
- ⚠️ No metrics collection
- ⚠️ Limited error context propagation
- ⚠️ No OpenTelemetry integration
- ⚠️ Missing error aggregation and analysis

---

## 1. Current Error Handling Assessment

### 1.1 Exception Hierarchy ✅

**Status:** Well-structured

```python
# src/startd8/exceptions.py
Startd8Error (base)
├── StorageError
│   └── FileOperationError
├── ValidationError
├── APIError (with retry context)
├── ConfigurationError
└── AgentError
```

**Strengths:**
- Clear exception hierarchy
- Context preservation (`original_error` fields)
- Specific error types for different domains

**Recommendations:**
- Add `error_code` field for programmatic error handling
- Add `severity` field (INFO, WARNING, ERROR, CRITICAL)
- Add `timestamp` field for error occurrence time

### 1.2 Logging Implementation ✅

**Status:** Good foundation, needs enhancement

**Current Implementation:**
```python
# src/startd8/logging_config.py
- JSONFormatter for structured logs
- Correlation ID support via ContextVar
- Configurable log levels
- File and console handlers
```

**Strengths:**
- Structured JSON logging
- Correlation ID tracking
- Configurable formatters

**Gaps:**
- No log sampling for high-volume scenarios
- No log aggregation/forwarding (will be addressed with Loki)
- Limited context propagation (only correlation_id)
- No log correlation with traces/metrics (will be addressed with OTel + Loki)
- No centralized log storage (will be addressed with Loki)

### 1.3 Error Handling Patterns ⚠️

**Status:** Inconsistent

#### Good Examples ✅

```python
# src/startd8/storage/base.py
@handle_storage_errors
def save(self, item: T) -> None:
    # Uses decorator, preserves context
    raise FileOperationError(...) from e
```

```python
# src/startd8/agents.py (some places)
raise APIError(
    f"API call failed: {str(e)}",
    provider=self.name,
    original_error=e
) from e
```

#### Areas Needing Improvement ⚠️

**Issue 1: Generic Exception Handling**
```python
# Found in multiple files
except Exception as e:
    logger.error(f"Error: {e}")
    # Loses context, no specific handling
```

**Issue 2: Silent Failures**
```python
# Some error paths don't log or re-raise
except Exception:
    pass  # Silent failure
```

**Issue 3: Missing Context**
```python
# Errors logged without sufficient context
logger.error(f"Failed: {e}")
# Missing: agent_name, request_id, operation, etc.
```

---

## 2. OpenTelemetry Integration Plan

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Application Layer                      │
│  (agents.py, orchestration.py, document_enhancement.py) │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              OpenTelemetry SDK Layer                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Traces     │  │   Metrics    │  │    Logs      │ │
│  │  (Spans)     │  │  (Counters,  │  │  (Events)    │ │
│  │              │  │   Gauges)    │  │              │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│              OTel Exporters/Collectors                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   OTLP      │  │   Console    │  │   File       │ │
│  │  (gRPC/HTTP)│  │   (Dev)      │  │   (Local)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────────────────┬────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────┐
│         Observability Backend (Grafana Stack)           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Tempo      │  │  Prometheus  │  │    Loki      │ │
│  │  (Traces)    │  │  (Metrics)   │  │   (Logs)     │ │
│  │              │  │              │  │              │ │
│  │  OTLP/gRPC   │  │  OTLP/gRPC   │  │  HTTP Push   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│              ┌──────────────────────┐                   │
│              │     Grafana          │                   │
│              │  (Visualization)     │                   │
│              └──────────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Implementation Phases

#### Phase 1: Foundation (Week 1-2)
**Goal:** Set up OTel SDK with Loki logging backend and basic instrumentation

**Tasks:**
1. Install OpenTelemetry dependencies (including Loki exporter dependencies)
2. Create OTel configuration module with Loki integration
3. Set up trace provider (exports to Tempo via OTLP at http://localhost:4317)
4. Set up metrics provider (exports to Prometheus via OTLP)
5. Set up logging provider with Loki exporter (exports to http://localhost:3100/loki/api/v1/push)
6. Integrate with existing logging infrastructure
7. Test Loki log export with existing Grafana stack (http://localhost:3000)
8. Verify logs appear in Grafana → Explore → Loki

**Deliverables:**
- `src/startd8/observability/otel_config.py`
- `src/startd8/observability/tracing.py`
- `src/startd8/observability/metrics.py`
- `src/startd8/observability/logging.py` (Loki integration)
- Updated `logging_config.py` with OTel log bridge and Loki exporter

#### Phase 2: Core Instrumentation (Week 3-4)
**Goal:** Instrument critical paths

**Tasks:**
1. Add tracing to agent operations (exported to Tempo at http://localhost:4317)
2. Add tracing to storage operations (exported to Tempo)
3. Add tracing to pipeline/workflow execution (exported to Tempo)
4. Add metrics for API calls, errors, latency (exported to Prometheus)
5. Add span context to logs (trace_id correlation in Loki)
6. Verify log-trace correlation in Grafana (http://localhost:3000)
7. Test queries in Grafana Explore view for logs and traces

**Deliverables:**
- Instrumented `agents.py`
- Instrumented `orchestration.py`
- Instrumented `storage/base.py`
- Instrumented `document_enhancement.py`

#### Phase 3: Advanced Features (Week 5-6)
**Goal:** Enhanced observability with Grafana integration

**Tasks:**
1. Add custom metrics (token usage, costs, etc.) - Prometheus
2. Add error tracking and aggregation - Loki queries in Grafana
3. Add performance profiling - Tempo traces
4. Add distributed tracing across async operations - Tempo
5. Add resource attributes
6. Create Grafana dashboards (http://localhost:3000) for unified observability
7. Set up log-trace correlation queries in Grafana Explore
8. Build dashboard panels showing logs, traces, and metrics together

**Deliverables:**
- Custom metrics exporters
- Error tracking dashboard queries
- Performance profiling integration
- Async trace propagation

#### Phase 4: Production Readiness (Week 7-8)
**Goal:** Production deployment

**Tasks:**
1. Add sampling strategies (trace sampling for Tempo)
2. Add exporter configuration (OTLP for Tempo/Prometheus, HTTP for Loki)
3. Add resource detection
4. Add health checks
5. Production Grafana dashboard templates (for http://localhost:3000)
6. Documentation and examples (including Grafana dashboard setup)
7. Log retention policies for Loki (configure in your existing Loki instance)
8. Export dashboard JSON for easy import into Grafana

**Deliverables:**
- Production configuration examples
- Documentation
- Monitoring dashboards
- Alerting rules

---

## 3. Detailed Implementation

### 3.1 OpenTelemetry Configuration

**File:** `src/startd8/observability/otel_config.py`

```python
"""
OpenTelemetry configuration for startd8 SDK
"""
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.console import ConsoleSpanExporter, ConsoleMetricExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry._logs import set_logger_provider
import os
from pathlib import Path

# Resource attributes
resource = Resource.create({
    "service.name": "startd8-sdk",
    "service.version": "1.0.0",
    "service.namespace": "startd8",
})

def setup_otel(
    enable_tracing: bool = True,
    enable_metrics: bool = True,
    enable_logging: bool = True,
    otlp_endpoint: str = None,
    loki_endpoint: str = None,
    console_export: bool = False,
    sampling_rate: float = 1.0
):
    """
    Set up OpenTelemetry instrumentation with Loki logging backend
    
    Args:
        enable_tracing: Enable distributed tracing (exports to Tempo via OTLP)
        enable_metrics: Enable metrics collection (exports to Prometheus via OTLP)
        enable_logging: Enable log correlation and export to Loki
        otlp_endpoint: OTLP endpoint URL for traces/metrics (e.g., "http://localhost:4317")
        loki_endpoint: Loki endpoint URL for logs (e.g., "http://localhost:3100/loki/api/v1/push")
        console_export: Export to console (for development)
        sampling_rate: Trace sampling rate (0.0 to 1.0)
    """
    # Tracing
    if enable_tracing:
        trace_provider = TracerProvider(resource=resource)
        
        # Add OTLP exporter if endpoint provided
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            trace_provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )
        
        # Add console exporter for development
        if console_export:
            console_exporter = ConsoleSpanExporter()
            trace_provider.add_span_processor(
                BatchSpanProcessor(console_exporter)
            )
        
        trace.set_tracer_provider(trace_provider)
    
    # Metrics
    if enable_metrics:
        metric_readers = []
        
        if otlp_endpoint:
            metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
            metric_readers.append(
                PeriodicExportingMetricReader(metric_exporter, export_interval_millis=5000)
            )
        
        if console_export:
            console_metric_exporter = ConsoleMetricExporter()
            metric_readers.append(
                PeriodicExportingMetricReader(console_metric_exporter, export_interval_millis=5000)
            )
        
        if metric_readers:
            metrics.set_meter_provider(
                MeterProvider(resource=resource, metric_readers=metric_readers)
            )
    
    # Logging integration with Loki
    if enable_logging:
        from .logging import setup_loki_logging
        
        # Set up OTel logger provider
        logger_provider = LoggerProvider(resource=resource)
        
        # Add Loki exporter if endpoint provided
        if loki_endpoint:
            from .logging import LokiLogExporter
            import os
            batch_size = int(os.getenv("LOKI_BATCH_SIZE", "100"))
            timeout = int(os.getenv("LOKI_TIMEOUT", "5"))
            
            loki_exporter = LokiLogExporter(
                endpoint=loki_endpoint,
                timeout=timeout
            )
            logger_provider.add_log_record_processor(
                BatchLogRecordProcessor(
                    loki_exporter,
                    max_queue_size=batch_size * 2,
                    export_timeout_millis=timeout * 1000
                )
            )
        
        set_logger_provider(logger_provider)
        
        # Bridge Python logging to OTel
        LoggingInstrumentor().instrument(set_logging_format=True)
        
        # Set up Loki-specific logging handler
        setup_loki_logging(loki_endpoint=loki_endpoint)
    
    return trace_provider, metrics.get_meter_provider()
```

### 3.2 Tracing Integration

**File:** `src/startd8/observability/tracing.py`

```python
"""
Tracing utilities for startd8 SDK
"""
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from functools import wraps
from typing import Optional, Dict, Any
import time

tracer = trace.get_tracer(__name__)

def trace_function(
    operation_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Decorator to trace function execution
    
    Usage:
        @trace_function(operation_name="agent.generate", attributes={"agent": "claude"})
        def generate(self, prompt: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            attrs = attributes or {}
            
            with tracer.start_as_current_span(op_name, attributes=attrs) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator

def trace_async_function(
    operation_name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None
):
    """
    Decorator to trace async function execution
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            attrs = attributes or {}
            
            with tracer.start_as_current_span(op_name, attributes=attrs) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator

class TraceContext:
    """Context manager for manual span creation"""
    
    def __init__(self, operation_name: str, attributes: Optional[Dict[str, Any]] = None):
        self.operation_name = operation_name
        self.attributes = attributes or {}
        self.span = None
    
    def __enter__(self):
        self.span = tracer.start_span(self.operation_name, attributes=self.attributes)
        return self.span
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            self.span.record_exception(exc_val)
        else:
            self.span.set_status(Status(StatusCode.OK))
        self.span.end()
```

### 3.3 Metrics Integration

**File:** `src/startd8/observability/metrics.py`

```python
"""
Metrics collection for startd8 SDK
"""
from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, UpDownCounter
from typing import Optional, Dict, Any

meter = metrics.get_meter(__name__)

# Define metrics
api_calls_total = meter.create_counter(
    "startd8_api_calls_total",
    description="Total number of API calls",
    unit="1"
)

api_call_duration = meter.create_histogram(
    "startd8_api_call_duration_ms",
    description="API call duration in milliseconds",
    unit="ms"
)

api_errors_total = meter.create_counter(
    "startd8_api_errors_total",
    description="Total number of API errors",
    unit="1"
)

tokens_used_total = meter.create_counter(
    "startd8_tokens_used_total",
    description="Total tokens used",
    unit="1"
)

cost_total = meter.create_counter(
    "startd8_cost_total",
    description="Total cost in USD",
    unit="USD"
)

active_spans = meter.create_up_down_counter(
    "startd8_active_spans",
    description="Number of active spans",
    unit="1"
)

def record_api_call(
    provider: str,
    model: str,
    duration_ms: float,
    success: bool,
    tokens: Optional[int] = None,
    cost: Optional[float] = None,
    error_type: Optional[str] = None
):
    """
    Record API call metrics
    
    Args:
        provider: Provider name (e.g., "anthropic", "openai")
        model: Model name (e.g., "claude-3-opus")
        duration_ms: Call duration in milliseconds
        success: Whether call succeeded
        tokens: Number of tokens used
        cost: Cost in USD
        error_type: Error type if failed
    """
    attributes = {
        "provider": provider,
        "model": model,
        "success": str(success)
    }
    
    # Record call count
    api_calls_total.add(1, attributes=attributes)
    
    # Record duration
    api_call_duration.record(duration_ms, attributes=attributes)
    
    # Record errors
    if not success and error_type:
        error_attrs = {**attributes, "error_type": error_type}
        api_errors_total.add(1, attributes=error_attrs)
    
    # Record tokens
    if tokens:
        token_attrs = {**attributes, "token_type": "total"}
        tokens_used_total.add(tokens, attributes=token_attrs)
    
    # Record cost
    if cost:
        cost_attrs = {**attributes}
        cost_total.add(cost, attributes=cost_attrs)
```

### 3.4 Loki Logging Integration

**File:** `src/startd8/observability/logging.py`

```python
"""
Loki logging integration for OpenTelemetry
"""
import json
import time
import httpx
from typing import Optional, Dict, Any, List
from opentelemetry.sdk._logs import LogRecord
from opentelemetry.sdk._logs.export import LogExporter, LogExportResult
from opentelemetry._logs import get_logger_provider
from opentelemetry import trace
from ..logging_config import get_logger

logger = get_logger(__name__)


class LokiLogExporter(LogExporter):
    """
    Exports logs to Grafana Loki via HTTP Push API
    
    Loki expects logs in a specific format:
    {
        "streams": [
            {
                "stream": { "label1": "value1", "label2": "value2" },
                "values": [["timestamp_ns", "log_line"], ...]
            }
        ]
    }
    
    Labels are used for indexing and filtering. Keep label cardinality low
    (avoid high-cardinality values like request IDs, timestamps).
    
    Trace correlation is achieved by including trace_id as a label, allowing
    queries like: {service="startd8-sdk", trace_id="abc123"}
    """
    
    def __init__(self, endpoint: str, timeout: int = 5):
        """
        Initialize Loki exporter
        
        Args:
            endpoint: Loki push endpoint (e.g., "http://localhost:3100/loki/api/v1/push")
                     Can be base URL or full push endpoint
            timeout: HTTP request timeout in seconds
        """
        self.endpoint = endpoint.rstrip('/')
        if not self.endpoint.endswith('/loki/api/v1/push'):
            # Handle both base URL and full endpoint
            if not self.endpoint.endswith('/loki'):
                self.endpoint = f"{self.endpoint}/loki/api/v1/push"
            else:
                self.endpoint = f"{self.endpoint}/api/v1/push"
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)
    
    def export(self, batch: List[LogRecord]) -> LogExportResult:
        """
        Export log records to Loki
        
        Args:
            batch: List of log records to export
            
        Returns:
            LogExportResult indicating success or failure
        """
        if not batch:
            return LogExportResult.SUCCESS
        
        try:
            # Group logs by labels (service, level, etc.)
            streams = {}
            
            for record in batch:
                # Extract labels from resource and record attributes
                labels = self._extract_labels(record)
                label_key = json.dumps(labels, sort_keys=True)
                
                if label_key not in streams:
                    streams[label_key] = {
                        "stream": labels,
                        "values": []
                    }
                
                # Convert log record to Loki format
                timestamp_ns = int(record.timestamp * 1e9)
                log_line = self._format_log_line(record)
                
                streams[label_key]["values"].append([str(timestamp_ns), log_line])
            
            # Send to Loki
            payload = {"streams": list(streams.values())}
            
            response = self._client.post(
                self.endpoint,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 204:
                return LogExportResult.SUCCESS
            else:
                logger.warning(
                    f"Loki export failed: {response.status_code} - {response.text}",
                    extra={"endpoint": self.endpoint}
                )
                return LogExportResult.FAILURE
                
        except Exception as e:
            logger.error(f"Failed to export logs to Loki: {e}", exc_info=True)
            return LogExportResult.FAILURE
    
    def _extract_labels(self, record: LogRecord) -> Dict[str, str]:
        """
        Extract labels from log record for Loki stream
        
        Labels should be LOW-cardinality (service name, level, etc.)
        High-cardinality values (like request IDs, timestamps) should NOT be labels.
        
        Loki best practices:
        - Keep label cardinality < 100 unique values per label
        - Use labels for filtering, not for storing data
        - Store high-cardinality data in the log line JSON instead
        """
        labels = {
            "service": "startd8-sdk",
            "level": record.severity_text or getattr(record.severity_number, 'name', 'UNKNOWN'),
        }
        
        # Add resource attributes as labels (if low-cardinality)
        if record.resource:
            for key, value in record.resource.attributes.items():
                if isinstance(value, (str, int, float, bool)):
                    # Only add low-cardinality resource attributes as labels
                    # Skip high-cardinality ones like instance_id, hostname variations
                    if key in ['service.name', 'service.version', 'deployment.environment']:
                        # Sanitize label key (Loki requirements: alphanumeric + _)
                        label_key = key.replace(".", "_").replace("-", "_")
                        labels[label_key] = str(value)
        
        # Add trace context if available (trace_id is high-cardinality but needed for correlation)
        # Note: This creates high-cardinality labels, but trace correlation is essential
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_ctx = span.get_span_context()
            # Format trace_id as hex string (32 hex chars)
            labels["trace_id"] = format(span_ctx.trace_id, '032x')
        
        # Add logger name (limited cardinality - only top-level logger)
        if record.name:
            # Use only the main logger name, not full path (e.g., "startd8" not "startd8.agents.claude")
            logger_name = record.name.split('.')[0]
            labels["logger"] = logger_name
        
        return labels
    
    def _format_log_line(self, record: LogRecord) -> str:
        """
        Format log record as JSON string for Loki
        
        Loki stores log lines as strings, so we JSON-encode the structured data.
        High-cardinality data (agent names, model names, request IDs) goes here,
        not in labels.
        """
        log_data = {
            "message": record.body if hasattr(record, 'body') else str(record),
            "logger": record.name,
            "level": record.severity_text or getattr(record.severity_number, 'name', 'UNKNOWN'),
        }
        
        # Add attributes (high-cardinality data stored in log line, not labels)
        if record.attributes:
            for k, v in record.attributes.items():
                # Convert values to JSON-serializable format
                if isinstance(v, (str, int, float, bool, type(None))):
                    log_data[str(k)] = v
                else:
                    log_data[str(k)] = str(v)
        
        # Add exception info if present
        if hasattr(record, 'exception') and record.exception:
            exc = record.exception
            log_data["exception"] = {
                "type": exc.type.__name__ if hasattr(exc, 'type') and exc.type else None,
                "message": str(exc) if exc else None,
            }
            # Include traceback if available
            if hasattr(exc, 'traceback') and exc.traceback:
                log_data["exception"]["traceback"] = exc.traceback
        
        # Add span context for correlation (if not already in labels)
        span = trace.get_current_span()
        if span and span.get_span_context().is_valid:
            span_ctx = span.get_span_context()
            log_data["span_id"] = format(span_ctx.span_id, '016x')
            # trace_id is already in labels, but include here too for convenience
        
        return json.dumps(log_data, ensure_ascii=False)
    
    def shutdown(self) -> None:
        """Shutdown the exporter"""
        self._client.close()


def setup_loki_logging(
    loki_endpoint: Optional[str] = None,
    enable_console: bool = True,
    batch_size: int = 100,
    timeout: int = 5
) -> None:
    """
    Set up logging to export to Loki
    
    Args:
        loki_endpoint: Loki push endpoint URL (defaults to LOKI_ENDPOINT env var)
        enable_console: Also log to console (for development)
        batch_size: Number of log records to batch before sending
        timeout: HTTP request timeout in seconds
    """
    if not loki_endpoint:
        loki_endpoint = os.getenv("LOKI_ENDPOINT")
    
    if loki_endpoint:
        logger_provider = get_logger_provider()
        loki_exporter = LokiLogExporter(
            endpoint=loki_endpoint,
            timeout=timeout
        )
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                loki_exporter,
                max_queue_size=batch_size * 2,
                export_timeout_millis=timeout * 1000
            )
        )
        logger.info(
            f"Loki logging enabled: {loki_endpoint}",
            extra={"loki_endpoint": loki_endpoint, "batch_size": batch_size}
        )
    else:
        logger.info("Loki endpoint not configured, skipping Loki export")
```

### 3.5 Enhanced Error Handling with OTel

**File:** `src/startd8/observability/error_tracking.py`

```python
"""
Enhanced error tracking with OpenTelemetry
"""
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from typing import Optional, Dict, Any
from ..exceptions import Startd8Error
from ..logging_config import get_logger

logger = get_logger(__name__)
tracer = trace.get_tracer(__name__)

def track_error(
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
    severity: str = "ERROR"
):
    """
    Track error with full context in traces and logs
    
    Args:
        error: Exception instance
        context: Additional context dictionary
        severity: Error severity (ERROR, WARNING, CRITICAL)
    """
    span = trace.get_current_span()
    
    # Add error to current span
    if span.is_recording():
        span.set_status(Status(StatusCode.ERROR, str(error)))
        span.record_exception(error)
        
        # Add context as span attributes
        if context:
            for key, value in context.items():
                span.set_attribute(f"error.{key}", str(value))
        
        # Add error-specific attributes
        if isinstance(error, Startd8Error):
            span.set_attribute("error.type", error.__class__.__name__)
            if hasattr(error, 'provider'):
                span.set_attribute("error.provider", error.provider)
            if hasattr(error, 'agent_name'):
                span.set_attribute("error.agent_name", error.agent_name)
            if hasattr(error, 'file_path'):
                span.set_attribute("error.file_path", error.file_path)
    
    # Log with structured context
    log_context = {
        "error_type": error.__class__.__name__,
        "error_message": str(error),
        "severity": severity
    }
    
    if context:
        log_context.update(context)
    
    logger.error(
        f"Error occurred: {error.__class__.__name__}: {error}",
        exc_info=True,
        extra=log_context
    )
```

### 3.5 Integration Examples

#### Example 1: Instrument Agent Operations

```python
# src/startd8/agents.py
from ..observability.tracing import trace_async_function, TraceContext
from ..observability.metrics import record_api_call
from ..observability.error_tracking import track_error
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class ClaudeAgent(BaseAgent):
    @trace_async_function(operation_name="agent.generate", attributes={"agent": "claude"})
    async def agenerate(self, prompt: str) -> Tuple[str, int, TokenUsage]:
        start_time = time.time()
        span = trace.get_current_span()
        
        try:
            span.set_attribute("agent.name", self.name)
            span.set_attribute("agent.model", self.model)
            span.set_attribute("prompt.length", len(prompt))
            
            response = await self._client.messages.create(...)
            
            duration_ms = (time.time() - start_time) * 1000
            tokens = response.usage
            
            # Record metrics
            record_api_call(
                provider="anthropic",
                model=self.model,
                duration_ms=duration_ms,
                success=True,
                tokens=tokens.input_tokens + tokens.output_tokens,
                cost=self._calculate_cost(tokens)
            )
            
            return response_text, duration_ms, token_usage
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            
            # Track error
            track_error(
                e,
                context={
                    "agent": self.name,
                    "model": self.model,
                    "duration_ms": duration_ms
                }
            )
            
            # Record error metrics
            record_api_call(
                provider="anthropic",
                model=self.model,
                duration_ms=duration_ms,
                success=False,
                error_type=e.__class__.__name__
            )
            
            raise
```

#### Example 2: Instrument Pipeline Execution

```python
# src/startd8/orchestration.py
from ..observability.tracing import TraceContext
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class Pipeline:
    def run(self, input_text: str) -> PipelineResult:
        with TraceContext(
            "pipeline.run",
            attributes={
                "pipeline.name": self.name,
                "pipeline.steps": len(self.steps)
            }
        ) as span:
            for i, step in enumerate(self.steps):
                with tracer.start_span(
                    f"pipeline.step.{step.name}",
                    attributes={
                        "step.number": i + 1,
                        "step.name": step.name,
                        "agent": step.agent.name
                    }
                ) as step_span:
                    try:
                        result = step.agent.generate(...)
                        step_span.set_attribute("step.success", True)
                    except Exception as e:
                        step_span.set_status(Status(StatusCode.ERROR, str(e)))
                        step_span.record_exception(e)
                        raise
```

---

## 4. Migration Strategy

### 4.1 Step-by-Step Migration

**Step 1: Add Dependencies**
```bash
# Core OpenTelemetry
pip install opentelemetry-api opentelemetry-sdk
pip install opentelemetry-exporter-otlp-proto-grpc

# Logging integration
pip install opentelemetry-instrumentation-logging

# Loki integration (HTTP client for Loki Push API)
pip install httpx>=0.24.0

# Optional: If opentelemetry-exporter-loki package exists
# pip install opentelemetry-exporter-loki
```

**Step 2: Create Observability Module**
- Create `src/startd8/observability/` directory
- Add configuration, tracing, metrics modules
- Update `__init__.py` exports

**Step 3: Initialize OTel in Framework**
```python
# src/startd8/framework.py
from .observability.otel_config import setup_otel
import os

class AgentFramework:
    def __init__(self, ...):
        # Initialize OTel with Loki integration
        # Uses environment variables for configuration
        setup_otel(
            enable_tracing=True,
            enable_metrics=True,
            enable_logging=True,
            otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
            loki_endpoint=os.getenv("LOKI_ENDPOINT", "http://localhost:3100/loki/api/v1/push"),
            console_export=os.getenv("OTEL_CONSOLE_EXPORT", "false").lower() == "true"
        )
```

**Step 4: Instrument Core Modules**
- Start with `agents.py` (highest value)
- Then `orchestration.py`
- Then `storage/base.py`
- Then `document_enhancement.py`

**Step 5: Update Error Handling**
- Replace generic exception handlers
- Add error tracking calls
- Ensure context propagation

**Step 6: Add Metrics**
- Add metrics to critical paths
- Create dashboards
- Set up alerts

### 4.2 Backward Compatibility

- OTel is opt-in via environment variables
- Default to console export for development
- No breaking changes to existing APIs
- Gradual rollout possible

---

## 5. Benefits

### 5.1 Debugging
- **Distributed Tracing:** See full request flow across async operations (Tempo)
- **Error Context:** Rich error context in traces and logs (Loki)
- **Correlation:** Link logs, traces, and metrics via trace_id across Grafana
- **Log Aggregation:** Centralized log storage and querying with Loki
- **Unified View:** Grafana dashboards showing logs, traces, and metrics together

### 5.2 Performance Monitoring
- **Latency Tracking:** Identify bottlenecks in pipelines
- **Resource Usage:** Track token usage and costs
- **Error Rates:** Monitor error rates by provider/model

### 5.3 Production Operations
- **Alerting:** Set up Grafana alerts on error rates, latency (from Prometheus metrics)
- **Dashboards:** Unified Grafana dashboards showing logs (Loki), traces (Tempo), and metrics (Prometheus)
- **Root Cause Analysis:** Quickly identify issue sources by correlating logs and traces via trace_id
- **Log Retention:** Configure Loki retention policies for cost management
- **Query Performance:** Optimize LogQL queries for efficient log analysis

---

## 6. Configuration Examples

### 6.1 Development (Console Export + Grafana Stack)
```bash
# Enable console export for local development
export OTEL_CONSOLE_EXPORT=true
export OTEL_LOG_LEVEL=DEBUG

# Also export to your existing Grafana stack
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push
export OTEL_SERVICE_NAME=startd8-sdk
```

**Note:** With `OTEL_CONSOLE_EXPORT=true`, logs will appear both in console (for immediate feedback) and in Loki (for Grafana analysis).

### 6.2 Production (Grafana Stack)
```bash
# Traces to Tempo (OTLP gRPC)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://tempo:4317
export OTEL_SERVICE_NAME=startd8-sdk
export OTEL_RESOURCE_ATTRIBUTES="service.version=1.0.0,deployment.environment=production"
export OTEL_TRACES_SAMPLER=traceidratio
export OTEL_TRACES_SAMPLER_ARG=0.1  # 10% sampling

# Metrics to Prometheus (via OTLP)
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://prometheus:4317

# Logs to Loki (HTTP Push API)
export LOKI_ENDPOINT=http://loki:3100/loki/api/v1/push
export LOKI_BATCH_SIZE=100  # Batch logs before sending
export LOKI_TIMEOUT=5  # HTTP timeout in seconds
```

**Note:** Adjust hostnames (`tempo`, `prometheus`, `loki`) based on your production infrastructure.
For local development with existing stack, use `localhost` instead.

### 6.3 Local Testing (Existing Grafana Stack)

**Note:** You already have a Grafana stack running at http://localhost:3000. Skip the Docker Compose setup below and proceed directly to SDK configuration.

**Optional: Docker Compose Reference (for reference only):**

If you need to set up a new stack elsewhere, here's a Docker Compose example:

Create `docker-compose.grafana-stack.yml`:
```yaml
version: '3.8'

services:
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - loki-data:/loki
  
  tempo:
    image: grafana/tempo:latest
    ports:
      - "4317:4317"  # OTLP gRPC
      - "4318:4318"  # OTLP HTTP
      - "3200:3200"  # Tempo HTTP
    command: ["-config.file=/etc/tempo.yaml"]
    volumes:
      - tempo-data:/var/tempo
  
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
  
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_FEATURE_TOGGLES_ENABLE=traceqlEditor
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    depends_on:
      - loki
      - tempo
      - prometheus

volumes:
  loki-data:
  tempo-data:
  prometheus-data:
  grafana-data:
```

**Start the stack (only if setting up new stack):**
```bash
docker-compose -f docker-compose.grafana-stack.yml up -d
```

**Configure SDK for Your Existing Stack:**
```bash
# Traces to Tempo
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Metrics to Prometheus (via OTLP)
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:4317

# Logs to Loki
export LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push

# Service configuration
export OTEL_SERVICE_NAME=startd8-sdk
export OTEL_RESOURCE_ATTRIBUTES="service.version=1.0.0,deployment.environment=local"

# Optional: Enable console export for development
export OTEL_CONSOLE_EXPORT=true
```

**Access Grafana:**
- Open http://localhost:3000
- Logs: Explore → Select Loki data source → Query logs using LogQL
- Traces: Explore → Select Tempo data source → Query traces using TraceQL
- Metrics: Explore → Select Prometheus data source → Query metrics using PromQL
- Dashboards: Create unified dashboards correlating all three data sources

**Grafana Data Source Configuration:**

Your Grafana stack at http://localhost:3000 should already have data sources configured. Verify:

1. **Check Existing Data Sources:**
   - Open http://localhost:3000
   - Go to Configuration → Data Sources
   - Verify Loki, Tempo, and Prometheus are configured

2. **If Data Sources Need Configuration:**

   **Loki Data Source:**
   - URL: Usually `http://loki:3100` (internal) or `http://localhost:3100` (external)
   - Access: Server (default)

   **Tempo Data Source:**
   - URL: Usually `http://tempo:3200` (internal) or `http://localhost:3200` (external)
   - Access: Server (default)
   - Enable "Search" and "Service Map"

   **Prometheus Data Source:**
   - URL: Usually `http://prometheus:9090` (internal) or `http://localhost:9090` (external)
   - Access: Server (default)

3. **Note:** The SDK will push logs to Loki, traces to Tempo, and metrics to Prometheus. 
   Make sure these services are accessible from your application.

### 6.4 Local Development Configuration (Existing Grafana Stack)

**For your existing Grafana stack at http://localhost:3000:**

```bash
# Traces to Tempo (OTLP gRPC)
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317

# Metrics to Prometheus (via OTLP)
export OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://localhost:4317

# Logs to Loki (HTTP Push API)
# Adjust port if your Loki instance uses a different port
export LOKI_ENDPOINT=http://localhost:3100/loki/api/v1/push

# Service configuration
export OTEL_SERVICE_NAME=startd8-sdk
export OTEL_RESOURCE_ATTRIBUTES="service.version=1.0.0,deployment.environment=local"

# Logging configuration
export OTEL_LOG_LEVEL=INFO

# Optional: Enable console export for development (logs also appear in console)
export OTEL_CONSOLE_EXPORT=true

# Optional: Loki batch configuration
export LOKI_BATCH_SIZE=100
export LOKI_TIMEOUT=5
```

**Quick Test:**

After setting environment variables, run a simple test to verify connectivity:

```python
from startd8.observability.otel_config import setup_otel
from startd8.observability.logging import setup_loki_logging
import logging

# Initialize OTel with Loki
setup_otel(
    enable_tracing=True,
    enable_metrics=True,
    enable_logging=True,
    otlp_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"),
    loki_endpoint=os.getenv("LOKI_ENDPOINT"),
    console_export=True
)

# Test logging
logger = logging.getLogger("startd8.test")
logger.info("Test log message - should appear in Loki")
```

Then check Grafana (http://localhost:3000) → Explore → Loki → Query: `{service="startd8-sdk"}`

**Expected Result:**
- Test log should appear in Grafana Explore → Loki
- You should see logs with `service="startd8-sdk"` label
- Logs will be JSON-formatted with trace_id if available

---

## 7. Success Metrics

- ✅ All critical paths instrumented with traces (exported to Tempo)
- ✅ Error tracking with full context (exported to Loki)
- ✅ Metrics for API calls, latency, errors (exported to Prometheus)
- ✅ Log correlation with traces via trace_id (Loki + Tempo)
- ✅ Unified observability in Grafana dashboards (http://localhost:3000)
- ✅ Production-ready configuration with existing Grafana stack
- ✅ Documentation and examples
- ✅ Logs visible in Grafana → Explore → Loki (http://localhost:3000)
- ✅ Traces visible in Grafana → Explore → Tempo (http://localhost:3000)
- ✅ Metrics visible in Grafana → Explore → Prometheus (http://localhost:3000)
- ✅ Unified dashboards showing correlated logs, traces, and metrics

---

## 8. Next Steps

1. **Review and Approve** this plan ✅
2. **Verify Grafana stack endpoints** (check http://localhost:3000 → Configuration → Data Sources)
   - Note Loki Push API endpoint (usually http://localhost:3100/loki/api/v1/push)
   - Note Tempo OTLP endpoint (usually http://localhost:4317)
   - Note Prometheus endpoint (usually http://localhost:9090)
3. **Set up OTel dependencies** and basic configuration
4. **Create observability module** structure with Loki exporter
5. **Configure environment variables** for your existing Grafana stack
6. **Test connectivity** - send test logs to Loki and verify in Grafana
7. **Instrument one module** as proof of concept
8. **Verify logs appear in Loki** (check Grafana → Explore → Loki at http://localhost:3000)
9. **Verify traces appear in Tempo** (check Grafana → Explore → Tempo)
10. **Create Grafana dashboards** for unified observability
11. **Iterate and expand** to other modules
12. **Document** usage patterns and dashboard setup

---

## Appendix: Dependencies

### Core OpenTelemetry
```txt
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp-proto-grpc>=1.20.0
opentelemetry-instrumentation-logging>=0.42b0
opentelemetry-instrumentation-httpx>=0.42b0  # For HTTP client tracing
```

### Loki Logging Backend
```txt
httpx>=0.24.0  # For Loki HTTP Push API
```

**Note:** We'll implement a custom Loki exporter using the Loki HTTP Push API since `opentelemetry-exporter-loki` may not be available or maintained. The exporter will format logs according to Loki's expected format and handle batching, retries, and error handling.

**Key Features of Loki Integration:**
- HTTP Push API integration (no additional dependencies beyond httpx)
- Automatic trace_id correlation for log-trace linking
- Low-cardinality label strategy for performance
- JSON-structured log lines with full context
- Batch processing for efficient log shipping
- Configurable timeouts and batch sizes

### Grafana Stack (Local Development)
**Note:** You already have a Grafana stack running at http://localhost:3000

**Your Existing Stack:**
- **Grafana UI**: http://localhost:3000 (already running)
- **Loki**: Check Grafana → Configuration → Data Sources → Loki for endpoint
- **Tempo**: Check Grafana → Configuration → Data Sources → Tempo for endpoint
- **Prometheus**: Check Grafana → Configuration → Data Sources → Prometheus for endpoint

**Common Default Ports:**
- **Loki**: http://localhost:3100 (Push API: http://localhost:3100/loki/api/v1/push)
- **Tempo**: http://localhost:4317 (OTLP gRPC) or http://localhost:4318 (OTLP HTTP)
- **Prometheus**: http://localhost:9090

**Verify your stack configuration:**
1. Open Grafana: http://localhost:3000
2. Go to Configuration → Data Sources
3. Check the URLs for Loki, Tempo, and Prometheus data sources
4. Use those URLs to configure the SDK endpoints (adjust ports if different)
5. For Loki, use the Push API endpoint: `http://<loki-host>:<loki-port>/loki/api/v1/push`

### Optional (for specific backends):
```txt
opentelemetry-exporter-jaeger>=1.20.0
opentelemetry-exporter-prometheus>=1.20.0
```

---

## Appendix: Loki Integration Details

### Loki Log Format
Loki expects logs in the following format via HTTP Push API:
```json
{
  "streams": [
    {
      "stream": {
        "service": "startd8-sdk",
        "level": "ERROR",
        "trace_id": "abc123..."
      },
      "values": [
        ["1234567890000000000", "{\"message\":\"Error occurred\",\"logger\":\"startd8.agents\"}"],
        ["1234567891000000000", "{\"message\":\"Another log\",\"logger\":\"startd8.orchestration\"}"]
      ]
    }
  ]
}
```

### Label Strategy
- **High-cardinality labels** (for filtering): `service`, `level`, `logger`
- **Trace correlation**: `trace_id` (from OpenTelemetry span context)
- **Low-cardinality**: Avoid labels with many unique values (e.g., timestamps, request IDs)
- **Best Practice**: Keep label cardinality low (< 100 unique values per label) for performance

### Log Line Format
- Logs are stored as JSON strings in Loki
- Includes: message, logger name, level, attributes, exception info
- Trace context automatically included when available
- Format: `{"message": "...", "logger": "...", "level": "ERROR", "trace_id": "...", ...}`

### Grafana Integration

**LogQL Queries (Loki):**
```logql
# All errors
{service="startd8-sdk", level="ERROR"}

# Errors with specific trace_id
{service="startd8-sdk", level="ERROR"} | json | trace_id="abc123..."

# Errors from specific logger
{service="startd8-sdk", logger="startd8.agents", level="ERROR"}

# Parse JSON and filter
{service="startd8-sdk"} | json | agent_name="claude-opus"
```

**TraceQL Queries (Tempo):**
```traceql
# Find traces with errors
{ status = error }

# Find traces by service
{ service.name = "startd8-sdk" }

# Find slow traces
{ duration > 5s }
```

**Correlation in Grafana:**
- Use `trace_id` to link logs and traces
- Example: Click on a log entry → View trace → See full request flow
- Example: Click on a trace span → View related logs → See all logs for that trace

**Dashboard Examples:**
- **Error Dashboard**: Logs from Loki filtered by `level="ERROR"` with trace links
- **Performance Dashboard**: Metrics from Prometheus (latency, throughput)
- **Trace Dashboard**: Traces from Tempo showing request flows
- **Unified Dashboard**: All three data sources with correlation
