"""
Verify Artisan pipeline OTel trace structure against a Tempo instance.

This module implements the 13 pipeline-specific verification checks (V-1–V-13)
required by REQ-PEM-000a Phase 1.  It queries a Tempo instance, reconstructs the
span hierarchy, and validates that the Artisan 8-phase pipeline produced the
expected span structure: workflow root, phase spans, gate spans, per-task spans,
LLM call spans, and correct parent-child relationships.

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
from fnmatch import fnmatch
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
# TRACE VERIFIER CLASS — Pipeline-Specific V-1–V-13 Checks (REQ-PEM-000a)
# ============================================================================

# Expected Artisan pipeline phase span names
_EXPECTED_PHASES = {
    "phase.plan", "phase.scaffold", "phase.design", "phase.implement",
    "phase.integrate", "phase.test", "phase.review", "phase.finalize",
}


class TraceVerifier:
    """Orchestrates the 13 pipeline-specific verification checks (V-1–V-13).

    Each check validates a structural property of the Artisan 8-phase pipeline
    trace, not generic OTel health.  This is required by REQ-PEM-000a Phase 1.
    """

    def __init__(self, spans: dict[str, SpanInfo], trace_id: str,
                 service_name: str = DEFAULT_SERVICE_NAME):
        self.spans = spans
        self.trace_id = trace_id
        self.service_name = service_name

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _get_ancestors(self, span_id: str) -> list[SpanInfo]:
        """Walk the parent chain from *span_id* up to (and including) the root."""
        ancestors: list[SpanInfo] = []
        current = self.spans.get(span_id)
        while current and current.parent_span_id:
            parent = self.spans.get(current.parent_span_id)
            if parent is None:
                break
            ancestors.append(parent)
            current = parent
        return ancestors

    def _has_ancestor_matching(self, span_id: str, pattern: str) -> bool:
        """Return True if any ancestor span name matches *pattern* (fnmatch)."""
        return any(fnmatch(a.name, pattern) for a in self._get_ancestors(span_id))

    # ------------------------------------------------------------------
    # V-1 – V-13 checks
    # ------------------------------------------------------------------

    def run_all_checks(self) -> VerificationReport:
        """Run all 13 pipeline-specific checks and return aggregate report."""
        report = VerificationReport(trace_id=self.trace_id)
        checks = [
            self.check_root_workflow_span,           # V-1
            self.check_all_phase_spans,              # V-2
            self.check_gate_entry_spans,             # V-3
            self.check_gate_exit_spans,              # V-4
            self.check_per_task_spans,               # V-5
            self.check_design_iteration_spans,       # V-6
            self.check_design_generate_span,         # V-7
            self.check_implement_chunk_span,         # V-8
            self.check_test_generate_span,           # V-9
            self.check_design_review_span,           # V-10
            self.check_no_error_spans,               # V-11
            self.check_design_parented_by_task,      # V-12
            self.check_chunk_parented_by_task,       # V-13
        ]
        for check_fn in checks:
            report.results.append(check_fn())
        return report

    def check_root_workflow_span(self) -> VerificationResult:
        """V-1: Exactly one span whose name starts with 'workflow.'."""
        workflow_spans = [s for s in self.spans.values() if s.name.startswith("workflow.")]
        passed = len(workflow_spans) == 1
        return VerificationResult(
            check_name="V-1_root_workflow_span",
            passed=passed,
            message=f"Found {len(workflow_spans)} workflow.* span(s), expected 1",
            details={"workflow_span_names": [s.name for s in workflow_spans]},
        )

    def check_all_phase_spans(self) -> VerificationResult:
        """V-2: All 8 expected phase span names are present."""
        found_phases = {s.name for s in self.spans.values() if s.name in _EXPECTED_PHASES}
        missing = _EXPECTED_PHASES - found_phases
        passed = len(missing) == 0
        return VerificationResult(
            check_name="V-2_all_phase_spans",
            passed=passed,
            message="All 8 phases present" if passed else f"Missing phases: {sorted(missing)}",
            details={"found": sorted(found_phases), "missing": sorted(missing)},
        )

    def check_gate_entry_spans(self) -> VerificationResult:
        """V-3: >=8 'gate.entry' spans with gate.passed + gate.propagation_status attrs."""
        gate_entries = [
            s for s in self.spans.values()
            if s.name == "gate.entry"
            and "gate.passed" in s.attributes
            and "gate.propagation_status" in s.attributes
        ]
        passed = len(gate_entries) >= 8
        return VerificationResult(
            check_name="V-3_gate_entry_spans",
            passed=passed,
            message=f"Found {len(gate_entries)} gate.entry span(s) with required attrs (need >=8)",
            details={"count": len(gate_entries)},
        )

    def check_gate_exit_spans(self) -> VerificationResult:
        """V-4: >=8 'gate.exit' spans with gate.passed attr."""
        gate_exits = [
            s for s in self.spans.values()
            if s.name == "gate.exit" and "gate.passed" in s.attributes
        ]
        passed = len(gate_exits) >= 8
        return VerificationResult(
            check_name="V-4_gate_exit_spans",
            passed=passed,
            message=f"Found {len(gate_exits)} gate.exit span(s) with gate.passed attr (need >=8)",
            details={"count": len(gate_exits)},
        )

    def check_per_task_spans(self) -> VerificationResult:
        """V-5: >=4 'task.*' spans with task.id + task.status attrs."""
        task_spans = [
            s for s in self.spans.values()
            if fnmatch(s.name, "task.*")
            and "task.id" in s.attributes
            and "task.status" in s.attributes
        ]
        passed = len(task_spans) >= 4
        return VerificationResult(
            check_name="V-5_per_task_spans",
            passed=passed,
            message=f"Found {len(task_spans)} task.* span(s) with required attrs (need >=4)",
            details={"count": len(task_spans), "task_names": [s.name for s in task_spans[:10]]},
        )

    def check_design_iteration_spans(self) -> VerificationResult:
        """V-6: >=1 'design.iteration.*' spans."""
        iteration_spans = [s for s in self.spans.values() if fnmatch(s.name, "design.iteration.*")]
        passed = len(iteration_spans) >= 1
        return VerificationResult(
            check_name="V-6_design_iteration_spans",
            passed=passed,
            message=f"Found {len(iteration_spans)} design.iteration.* span(s) (need >=1)",
            details={"count": len(iteration_spans)},
        )

    def check_design_generate_span(self) -> VerificationResult:
        """V-7: >=1 'design.generate' spans."""
        gen_spans = [s for s in self.spans.values() if s.name == "design.generate"]
        passed = len(gen_spans) >= 1
        return VerificationResult(
            check_name="V-7_design_generate_span",
            passed=passed,
            message=f"Found {len(gen_spans)} design.generate span(s) (need >=1)",
            details={"count": len(gen_spans)},
        )

    def check_implement_chunk_span(self) -> VerificationResult:
        """V-8: >=1 'implement.chunk.*' span with chunk.status attr."""
        chunk_spans = [
            s for s in self.spans.values()
            if fnmatch(s.name, "implement.chunk.*") and "chunk.status" in s.attributes
        ]
        passed = len(chunk_spans) >= 1
        return VerificationResult(
            check_name="V-8_implement_chunk_span",
            passed=passed,
            message=f"Found {len(chunk_spans)} implement.chunk.* span(s) with chunk.status (need >=1)",
            details={"count": len(chunk_spans)},
        )

    def check_test_generate_span(self) -> VerificationResult:
        """V-9: >=1 'test.generate' spans."""
        test_spans = [s for s in self.spans.values() if s.name == "test.generate"]
        passed = len(test_spans) >= 1
        return VerificationResult(
            check_name="V-9_test_generate_span",
            passed=passed,
            message=f"Found {len(test_spans)} test.generate span(s) (need >=1)",
            details={"count": len(test_spans)},
        )

    def check_design_review_span(self) -> VerificationResult:
        """V-10: >=1 'design.review.*' spans."""
        review_spans = [s for s in self.spans.values() if fnmatch(s.name, "design.review.*")]
        passed = len(review_spans) >= 1
        return VerificationResult(
            check_name="V-10_design_review_span",
            passed=passed,
            message=f"Found {len(review_spans)} design.review.* span(s) (need >=1)",
            details={"count": len(review_spans)},
        )

    def check_no_error_spans(self) -> VerificationResult:
        """V-11: No spans have status_code == 2 (ERROR)."""
        error_spans = [s for s in self.spans.values() if s.status_code == 2]
        passed = len(error_spans) == 0
        return VerificationResult(
            check_name="V-11_no_error_spans",
            passed=passed,
            message="No error spans" if passed else f"{len(error_spans)} span(s) have ERROR status",
            details={"error_span_ids": [s.span_id for s in error_spans],
                     "error_span_names": [s.name for s in error_spans]},
        )

    def check_design_parented_by_task(self) -> VerificationResult:
        """V-12: Every 'design.generate' span has a 'task.*' ancestor."""
        gen_spans = [s for s in self.spans.values() if s.name == "design.generate"]
        if not gen_spans:
            return VerificationResult(
                check_name="V-12_design_parented_by_task",
                passed=False,
                message="No design.generate spans found to verify parentage",
            )
        unparented = [
            s.span_id for s in gen_spans
            if not self._has_ancestor_matching(s.span_id, "task.*")
        ]
        passed = len(unparented) == 0
        return VerificationResult(
            check_name="V-12_design_parented_by_task",
            passed=passed,
            message="All design.generate spans parented by task.*" if passed
                    else f"{len(unparented)}/{len(gen_spans)} design.generate span(s) lack task.* ancestor",
            details={"unparented_span_ids": unparented, "total": len(gen_spans)},
        )

    def check_chunk_parented_by_task(self) -> VerificationResult:
        """V-13: Every 'implement.chunk.*' span has a 'task.*' ancestor."""
        chunk_spans = [s for s in self.spans.values() if fnmatch(s.name, "implement.chunk.*")]
        if not chunk_spans:
            return VerificationResult(
                check_name="V-13_chunk_parented_by_task",
                passed=False,
                message="No implement.chunk.* spans found to verify parentage",
            )
        unparented = [
            s.span_id for s in chunk_spans
            if not self._has_ancestor_matching(s.span_id, "task.*")
        ]
        passed = len(unparented) == 0
        return VerificationResult(
            check_name="V-13_chunk_parented_by_task",
            passed=passed,
            message="All implement.chunk.* spans parented by task.*" if passed
                    else f"{len(unparented)}/{len(chunk_spans)} implement.chunk.* span(s) lack task.* ancestor",
            details={"unparented_span_ids": unparented, "total": len(chunk_spans)},
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
