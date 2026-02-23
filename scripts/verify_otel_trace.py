"""
Verify OpenTelemetry trace instrumentation against a Tempo instance.

This module implements a programmatic trace verification script that validates
full-depth OTel instrumentation by querying a Tempo instance and verifying 13
specific checks against a Phase 0 trace. The script reconstructs the span
hierarchy and validates context propagation, span attributes, and structural
correctness.

Exit codes:
  0 = All 13 checks passed
  1 = One or more checks failed
  2 = Connection/infrastructure error (Tempo unreachable, no traces found)
"""

import json
import sys
import argparse
import time
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import requests

# ============================================================================
# CONSTANTS & CONFIGURATION
# ============================================================================

TEMPO_BASE_URL = "http://localhost:3200"
DEFAULT_SERVICE_NAME = "startd8"
REQUEST_TIMEOUT = 10
RETRY_ATTEMPTS = 3
RETRY_DELAY = 2.0
EXPECTED_CHECK_COUNT = 13

EXIT_CODE_SUCCESS = 0
EXIT_CODE_FAILURE = 1
EXIT_CODE_CONNECTION_ERROR = 2

# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================


class VerifyOtelError(Exception):
    """Base exception for the verification script."""


class TempoConnectionError(VerifyOtelError):
    """Cannot connect to Tempo."""


class TempoQueryError(VerifyOtelError):
    """Tempo returned an error response."""


class TraceNotFoundError(VerifyOtelError):
    """Requested trace ID not found in Tempo."""

# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class SpanInfo:
    """Parsed span from Tempo trace response."""
    span_id: str
    trace_id: str
    parent_span_id: str
    name: str
    kind: int  # 0=UNSPECIFIED, 1=INTERNAL, 2=SERVER, 3=CLIENT, 4=PRODUCER, 5=CONSUMER
    status_code: int  # 0=UNSET, 1=OK, 2=ERROR
    attributes: dict[str, Any]
    resource_attributes: dict[str, Any]
    scope_name: str
    start_time: int  # nanoseconds
    end_time: int  # nanoseconds
    events: list[dict[str, Any]]


@dataclass
class VerificationResult:
    """Result of a single verification check."""
    check_name: str
    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationReport:
    """Aggregate report of all 13 checks."""
    trace_id: str
    results: list[VerificationResult] = field(default_factory=list)
    
    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)
    
    @property
    def all_passed(self) -> bool:
        return len(self.results) == EXPECTED_CHECK_COUNT and all(r.passed for r in self.results)

    def to_dict(self) -> dict[str, Any]:
        """Serialize report for JSON output."""
        return {
            "trace_id": self.trace_id,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "all_passed": self.all_passed,
            "results": [
                {
                    "check_name": r.check_name,
                    "passed": r.passed,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.results
            ],
        }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def extract_attributes(attr_list: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert OTLP attribute list [{key, value: {stringValue|intValue|...}}] to dict.
    
    Handles all OTLP value types:
    - stringValue, intValue, boolValue, doubleValue: extracted directly
    - arrayValue, kvlistValue: stored as raw dict for downstream inspection
    """
    result: dict[str, Any] = {}
    for attr in attr_list:
        key = attr.get("key", "")
        value_obj = attr.get("value", {})
        # Primitive OTLP value types
        for vtype in ("stringValue", "intValue", "boolValue", "doubleValue"):
            if vtype in value_obj:
                result[key] = value_obj[vtype]
                break
        else:
            # Complex types: arrayValue, kvlistValue — store raw for inspection
            for vtype in ("arrayValue", "kvlistValue", "bytesValue"):
                if vtype in value_obj:
                    result[key] = value_obj[vtype]
                    break
    return result


def query_tempo(url: str, params: dict[str, str] | None = None, 
                timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    """Query Tempo HTTP API with retry logic.
    
    Retries on ConnectionError and Timeout (common transient failures).
    Raises TempoQueryError on HTTP error responses (4xx/5xx).
    Raises TempoConnectionError after all retry attempts are exhausted.
    """
    last_error: Exception | None = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = e
            if attempt < RETRY_ATTEMPTS - 1:
                time.sleep(RETRY_DELAY)
        except requests.exceptions.HTTPError as e:
            raise TempoQueryError(f"Tempo returned {resp.status_code}: {resp.text}") from e
        except json.JSONDecodeError as e:
            raise TempoQueryError(f"Invalid JSON response from Tempo: {e}") from e
    raise TempoConnectionError(
        f"Cannot reach Tempo after {RETRY_ATTEMPTS} attempts"
    ) from last_error


def fetch_trace(tempo_url: str, trace_id: str) -> dict[str, Any]:
    """Fetch a specific trace by ID from Tempo.
    
    Raises TraceNotFoundError if the trace is not found (404).
    """
    url = f"{tempo_url}/api/traces/{trace_id}"
    try:
        return query_tempo(url)
    except TempoQueryError as e:
        if "404" in str(e):
            raise TraceNotFoundError(f"Trace {trace_id} not found in Tempo") from e
        raise


def search_recent_traces(tempo_url: str, service_name: str = DEFAULT_SERVICE_NAME, 
                         limit: int = 1) -> list[str]:
    """Search for recent trace IDs by service name.
    
    Uses the requests `params` kwarg to properly encode query parameters
    rather than manual URL encoding, ensuring correctness across Tempo versions.
    
    Returns a list of trace IDs (strings), empty if no traces found.
    """
    url = f"{tempo_url}/api/search"
    params = {
        "q": f'{{resource.service.name="{service_name}"}}',
        "limit": str(limit),
    }
    data = query_tempo(url, params=params)
    traces = data.get("traces", [])
    return [t["traceID"] for t in traces]


def build_span_tree(trace_data: dict[str, Any]) -> dict[str, SpanInfo]:
    """Parse Tempo trace response into a span lookup keyed by spanID.
    
    Supports both Tempo response formats:
    - 'batches' key (v1 / older OTLP format)
    - 'resourceSpans' key (v2 / current OTLP format)
    
    Both formats are normalized into the same SpanInfo structure.
    
    Returns a dictionary mapping spanID -> SpanInfo.
    """
    spans: dict[str, SpanInfo] = {}
    
    # Normalize: support both 'batches' (v1) and 'resourceSpans' (v2) keys
    resource_span_batches = trace_data.get("batches", []) or trace_data.get("resourceSpans", [])
    
    for batch in resource_span_batches:
        resource_attrs = extract_attributes(batch.get("resource", {}).get("attributes", []))
        
        # Normalize: v1 uses 'scopeSpans'/'instrumentationLibrarySpans', v2 uses 'scopeSpans'
        scope_spans_list = (
            batch.get("scopeSpans", [])
            + batch.get("instrumentationLibrarySpans", [])
        )
        
        for scope_spans in scope_spans_list:
            scope_obj = scope_spans.get("scope") or scope_spans.get("instrumentationLibrary", {})
            scope_name = scope_obj.get("name", "") if scope_obj else ""
            for span in scope_spans.get("spans", []):
                info = SpanInfo(
                    span_id=span.get("spanId", ""),
                    trace_id=span.get("traceId", ""),
                    parent_span_id=span.get("parentSpanId", ""),
                    name=span.get("name", ""),
                    kind=span.get("kind", 0),
                    status_code=span.get("status", {}).get("code", 0),
                    attributes=extract_attributes(span.get("attributes", [])),
                    resource_attributes=resource_attrs,
                    scope_name=scope_name,
                    start_time=int(span.get("startTimeUnixNano", 0)),
                    end_time=int(span.get("endTimeUnixNano", 0)),
                    events=span.get("events", []),
                )
                spans[info.span_id] = info
    return spans


# ============================================================================
# TRACE VERIFIER CLASS
# ============================================================================


class TraceVerifier:
    """Orchestrates the 13 verification checks against a trace."""
    
    def __init__(self, spans: dict[str, SpanInfo], trace_id: str, 
                 service_name: str = DEFAULT_SERVICE_NAME):
        self.spans = spans
        self.trace_id = trace_id
        self.service_name = service_name
        self._root_spans: list[SpanInfo] = [
            s for s in spans.values() if not s.parent_span_id
        ]
    
    def run_all_checks(self) -> VerificationReport:
        """Run all 13 verification checks and return aggregate report."""
        report = VerificationReport(trace_id=self.trace_id)
        checks = [
            self.check_minimum_span_count,
            self.check_has_root_span,
            self.check_root_span_service_name,
            self.check_span_depth_minimum,
            self.check_all_spans_same_trace_id,
            self.check_parent_child_links_valid,
            self.check_all_spans_reachable_from_root,
            self.check_span_names_non_empty,
            self.check_span_timing_valid,
            self.check_status_codes_valid,
            self.check_resource_attributes_present,
            self.check_scope_instrumentation_present,
            self.check_context_propagation_intact,
        ]
        for check_fn in checks:
            report.results.append(check_fn())
        return report
    
    def check_minimum_span_count(self) -> VerificationResult:
        """Verify the trace contains at least 2 spans (meaningful instrumentation)."""
        count = len(self.spans)
        passed = count >= 2
        return VerificationResult(
            check_name="minimum_span_count",
            passed=passed,
            message=f"Trace contains {count} span(s)" if passed else f"Expected ≥2 spans, found {count}",
            details={"span_count": count},
        )

    def check_has_root_span(self) -> VerificationResult:
        """Verify exactly one root span exists."""
        root_count = len(self._root_spans)
        passed = root_count == 1
        return VerificationResult(
            check_name="has_root_span",
            passed=passed,
            message=f"Found {root_count} root span(s)" if passed else f"Expected 1 root span, found {root_count}",
            details={"root_span_count": root_count},
        )

    def check_root_span_service_name(self) -> VerificationResult:
        """Verify root span's resource service.name matches the expected service name."""
        if not self._root_spans:
            return VerificationResult(
                check_name="root_span_service_name",
                passed=False,
                message="No root span found to check service name",
            )
        root = self._root_spans[0]
        actual = root.resource_attributes.get("service.name", "")
        passed = actual == self.service_name
        return VerificationResult(
            check_name="root_span_service_name",
            passed=passed,
            message=f"service.name='{actual}'" if passed else f"Expected '{self.service_name}', got '{actual}'",
            details={"expected": self.service_name, "actual": actual},
        )

    def check_span_depth_minimum(self) -> VerificationResult:
        """Compute tree depth via BFS from root; require >= 2.
        
        Uses collections.deque for O(1) popleft instead of list.pop(0).
        """
        children_map: dict[str, list[str]] = {}
        for sid, span in self.spans.items():
            parent = span.parent_span_id
            if parent:
                children_map.setdefault(parent, []).append(sid)
        
        max_depth = 0
        if self._root_spans:
            queue: deque[tuple[str, int]] = deque([(self._root_spans[0].span_id, 1)])
            while queue:
                current, depth = queue.popleft()
                max_depth = max(max_depth, depth)
                for child_id in children_map.get(current, []):
                    queue.append((child_id, depth + 1))
        
        passed = max_depth >= 2
        return VerificationResult(
            check_name="span_depth_minimum",
            passed=passed,
            message=f"Span tree depth: {max_depth}",
            details={"max_depth": max_depth},
        )

    def check_all_spans_same_trace_id(self) -> VerificationResult:
        """Verify all spans share the same trace ID."""
        trace_ids = set(s.trace_id for s in self.spans.values())
        passed = len(trace_ids) == 1
        return VerificationResult(
            check_name="all_spans_same_trace_id",
            passed=passed,
            message=f"All spans share trace ID: {self.trace_id}" if passed else f"Found {len(trace_ids)} different trace IDs",
            details={"unique_trace_ids": len(trace_ids)},
        )

    def check_parent_child_links_valid(self) -> VerificationResult:
        """Verify structural link integrity: every non-root span's parentSpanId
        references a spanId that exists within the trace.
        
        This catches data corruption where a span claims a parent that was never recorded.
        Distinct from check_all_spans_reachable_from_root which validates graph connectivity.
        """
        invalid_links: list[dict[str, str]] = []
        for sid, span in self.spans.items():
            if span.parent_span_id and span.parent_span_id not in self.spans:
                invalid_links.append({"span_id": sid, "missing_parent": span.parent_span_id})
        passed = len(invalid_links) == 0
        return VerificationResult(
            check_name="parent_child_links_valid",
            passed=passed,
            message="All parent-child links valid" if passed else f"{len(invalid_links)} span(s) reference missing parents",
            details={"invalid_links": invalid_links},
        )

    def check_all_spans_reachable_from_root(self) -> VerificationResult:
        """Verify graph connectivity: every span is reachable from the root via BFS traversal.
        
        This catches disconnected subtrees where spans may have valid parent links
        to each other but form an island disconnected from the root (e.g., a subtree
        whose connecting span was dropped during collection).
        
        Distinct from check_parent_child_links_valid which only validates that
        referenced parent IDs exist.
        """
        if not self._root_spans:
            return VerificationResult(
                check_name="all_spans_reachable_from_root",
                passed=False,
                message="No root span found; cannot verify reachability",
            )
        
        children_map: dict[str, list[str]] = {}
        for sid, span in self.spans.items():
            if span.parent_span_id:
                children_map.setdefault(span.parent_span_id, []).append(sid)
        
        visited: set[str] = set()
        queue: deque[str] = deque([self._root_spans[0].span_id])
        while queue:
            current = queue.popleft()
            visited.add(current)
            for child_id in children_map.get(current, []):
                if child_id not in visited:
                    queue.append(child_id)
        
        unreachable = set(self.spans.keys()) - visited
        passed = len(unreachable) == 0
        return VerificationResult(
            check_name="all_spans_reachable_from_root",
            passed=passed,
            message="All spans reachable from root" if passed else f"{len(unreachable)} span(s) not reachable from root",
            details={"unreachable_span_ids": list(unreachable)},
        )

    def check_span_names_non_empty(self) -> VerificationResult:
        """Verify all spans have non-empty operation names."""
        empty_names = [
            s.span_id for s in self.spans.values() 
            if not s.name or not s.name.strip()
        ]
        passed = len(empty_names) == 0
        return VerificationResult(
            check_name="span_names_non_empty",
            passed=passed,
            message="All spans have non-empty names" if passed else f"{len(empty_names)} span(s) have empty names",
            details={"empty_name_span_ids": empty_names},
        )

    def check_span_timing_valid(self) -> VerificationResult:
        """Verify endTimeUnixNano >= startTimeUnixNano for all spans."""
        invalid_timings = [
            {"span_id": s.span_id, "start": s.start_time, "end": s.end_time}
            for s in self.spans.values()
            if s.end_time < s.start_time
        ]
        passed = len(invalid_timings) == 0
        return VerificationResult(
            check_name="span_timing_valid",
            passed=passed,
            message="All spans have valid timing" if passed else f"{len(invalid_timings)} span(s) have invalid timing",
            details={"invalid_timings": invalid_timings},
        )

    def check_status_codes_valid(self) -> VerificationResult:
        """Verify no span has STATUS_CODE_ERROR (code=2)."""
        error_spans = [
            s.span_id for s in self.spans.values() 
            if s.status_code == 2
        ]
        passed = len(error_spans) == 0
        return VerificationResult(
            check_name="status_codes_valid",
            passed=passed,
            message="No spans have error status" if passed else f"{len(error_spans)} span(s) have error status",
            details={"error_span_ids": error_spans},
        )

    def check_resource_attributes_present(self) -> VerificationResult:
        """Verify required resource attributes exist."""
        required_attrs = {"service.name", "telemetry.sdk.language"}
        missing_attrs = []
        for span in self.spans.values():
            for attr in required_attrs:
                if attr not in span.resource_attributes or not span.resource_attributes[attr]:
                    if attr not in [m["attr"] for m in missing_attrs if m["span_id"] == span.span_id]:
                        missing_attrs.append({"span_id": span.span_id, "attr": attr})
        
        passed = len(missing_attrs) == 0
        return VerificationResult(
            check_name="resource_attributes_present",
            passed=passed,
            message="All required resource attributes present" if passed else f"Missing required attributes in {len(set(m['span_id'] for m in missing_attrs))} span(s)",
            details={"missing_attributes": missing_attrs},
        )

    def check_scope_instrumentation_present(self) -> VerificationResult:
        """Verify at least one span has a non-empty instrumentation scope name."""
        instrumented_spans = [
            s.span_id for s in self.spans.values() 
            if s.scope_name and s.scope_name.strip()
        ]
        passed = len(instrumented_spans) > 0
        return VerificationResult(
            check_name="scope_instrumentation_present",
            passed=passed,
            message=f"{len(instrumented_spans)} span(s) have instrumentation scope" if passed else "No spans have instrumentation scope",
            details={"instrumented_span_ids": instrumented_spans},
        )

    def check_context_propagation_intact(self) -> VerificationResult:
        """Verify context propagation: child spans share parent's trace ID."""
        propagation_errors = []
        for span in self.spans.values():
            if span.parent_span_id and span.parent_span_id in self.spans:
                parent = self.spans[span.parent_span_id]
                if span.trace_id != parent.trace_id:
                    propagation_errors.append({
                        "child_span_id": span.span_id,
                        "parent_span_id": span.parent_span_id,
                        "child_trace_id": span.trace_id,
                        "parent_trace_id": parent.trace_id,
                    })
        
        passed = len(propagation_errors) == 0
        return VerificationResult(
            check_name="context_propagation_intact",
            passed=passed,
            message="Context propagation is intact" if passed else f"{len(propagation_errors)} propagation error(s)",
            details={"propagation_errors": propagation_errors},
        )


# ============================================================================
# REPORT OUTPUT
# ============================================================================


def print_report(report: VerificationReport) -> None:
    """Print human-readable verification report to stdout."""
    print(f"\n{'='*60}")
    print("OTel Trace Verification Report")
    print(f"Trace ID: {report.trace_id}")
    print(f"{'='*60}")
    for i, result in enumerate(report.results, 1):
        status = "✅ PASS" if result.passed else "❌ FAIL"
        print(f"  [{i:2d}/13] {status}  {result.check_name}: {result.message}")
    print(f"{'='*60}")
    print(f"Result: {report.passed_count}/13 checks passed")
    if report.all_passed:
        print("🎉 All verification checks PASSED")
    else:
        print(f"⚠️  {report.failed_count} check(s) FAILED")
    print()


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================


def main(tempo_url: str = TEMPO_BASE_URL, trace_id: str | None = None, 
         service_name: str = DEFAULT_SERVICE_NAME, json_output: bool = False) -> int:
    """Main entry point for trace verification.
    
    Args:
        tempo_url: Base URL of Tempo instance
        trace_id: Specific trace ID to verify (auto-discovers if omitted)
        service_name: Service name to filter traces for
        json_output: Output report as JSON
    
    Returns:
        Exit code: 0 (success), 1 (checks failed), 2 (connection error)
    """
    logger = logging.getLogger("verify_otel_trace")
    
    try:
        if trace_id is None:
            trace_ids = search_recent_traces(tempo_url, service_name=service_name)
            if not trace_ids:
                logger.error("No recent traces found for service '%s'", service_name)
                return EXIT_CODE_CONNECTION_ERROR
            trace_id = trace_ids[0]
        
        raw_trace = fetch_trace(tempo_url, trace_id)
        spans = build_span_tree(raw_trace)
        
        if not spans:
            logger.error("Trace %s contains no spans", trace_id)
            return EXIT_CODE_CONNECTION_ERROR
        
        verifier = TraceVerifier(spans, trace_id, service_name=service_name)
        report = verifier.run_all_checks()
        
        if json_output:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_report(report)
        
        return EXIT_CODE_SUCCESS if report.all_passed else EXIT_CODE_FAILURE
    
    except TempoConnectionError as e:
        logger.error("Tempo connection failed: %s", e)
        return EXIT_CODE_CONNECTION_ERROR
    except TempoQueryError as e:
        logger.error("Tempo query error: %s", e)
        return EXIT_CODE_CONNECTION_ERROR
    except TraceNotFoundError as e:
        logger.error("Trace not found: %s", e)
        return EXIT_CODE_CONNECTION_ERROR
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return EXIT_CODE_CONNECTION_ERROR


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify OTel trace instrumentation against Tempo"
    )
    parser.add_argument(
        "--tempo-url", 
        default=TEMPO_BASE_URL,
        help=f"Tempo base URL (default: {TEMPO_BASE_URL})"
    )
    parser.add_argument(
        "--trace-id",
        default=None,
        help="Specific trace ID (auto-discovers if omitted)"
    )
    parser.add_argument(
        "--service-name",
        default=DEFAULT_SERVICE_NAME,
        help=f"Service name to filter traces for (default: {DEFAULT_SERVICE_NAME})"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output report as JSON for programmatic consumption"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    
    sys.exit(main(
        tempo_url=args.tempo_url,
        trace_id=args.trace_id,
        service_name=args.service_name,
        json_output=args.json_output,
    ))
