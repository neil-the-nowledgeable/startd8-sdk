"""Validate the ResolvedPriceService suite adapter and proto provisioning."""
from __future__ import annotations

import socket
from concurrent import futures

import grpc
import pytest

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral import resolved_pricing_pb2_grpc
from startd8.benchmark_matrix.behavioral import resolved_pricing_suite


class _FixtureResolvedPricing(resolved_pricing_pb2_grpc.ResolvedPriceServiceServicer):
    """Fixture server that answers exactly the canonical S2 suite cases."""

    def __init__(self):
        cases = resolved_pricing_suite._case_module()
        self.valid_cases = [
            (
                resolved_pricing_suite.request_from_dict(case["request"]),
                resolved_pricing_suite.response_from_dict(case["expected_response"]),
            )
            for case in cases.VALID_CASES
        ]
        self.invalid_requests = []
        for case in cases.INVALID_CASES:
            try:
                self.invalid_requests.append(resolved_pricing_suite.request_from_dict(case["request"]))
            except Exception:  # noqa: BLE001 - some invalid fixtures are unencodable uint32 values
                pass

    def AssessLines(self, request, context):
        for expected_request, response in self.valid_cases:
            if request == expected_request:
                return response
        for expected_request in self.invalid_requests:
            if request == expected_request:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "fixture invalid request")
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "unknown fixture request")


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture()
def fixture_server():
    port = _free_port()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    resolved_pricing_pb2_grpc.add_ResolvedPriceServiceServicer_to_server(
        _FixtureResolvedPricing(), server
    )
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    try:
        yield port
    finally:
        server.stop(grace=None)


def test_resolved_suite_reaches_full_coverage_against_fixture(fixture_server):
    result = resolved_pricing_suite.run_resolved_pricing_suite(fixture_server)
    assert result.connect_error == "", result.connect_error
    failing = [(r.name, r.detail) for r in result.results if not r.passed]
    assert result.coverage == 1.0, f"failing checks: {failing}"
    assert len(result.results) == 24


def test_resolved_proto_mapping_keeps_existing_services_unchanged():
    default = (execute._PROTO, "demo.proto")
    for ob in ("paymentservice", "currencyservice", "shippingservice", "adservice", "checkoutservice"):
        assert execute._PROTO_BY_SERVICE.get(ob, default) == default
    assert execute._PROTO_BY_SERVICE["pricingservice"] == (execute._PRICING_PROTO, "pricing.proto")
    assert execute._PROTO_BY_SERVICE["resolvedpriceservice"] == (
        execute._RESOLVED_PRICING_PROTO,
        "pricing.proto",
    )


@pytest.mark.skipif(
    not (execute._NODE_RUNTIME / "node_modules").is_dir(),
    reason="node runtime not vendored - run node_runtime/vendor.sh",
)
def test_prepare_node_workdir_writes_resolved_pricing_proto(tmp_path):
    workdir = tmp_path / "resolved"
    assert execute.prepare_node_workdir(
        workdir,
        ["src/resolvedpriceservice/server.js"],
        proto_src=execute._RESOLVED_PRICING_PROTO,
        proto_name="pricing.proto",
    )
    expected = execute._RESOLVED_PRICING_PROTO.read_text(encoding="utf-8")
    assert (workdir / "pricing.proto").read_text(encoding="utf-8") == expected
    assert (workdir / "src/resolvedpriceservice/pricing.proto").read_text(encoding="utf-8") == expected
    assert not (workdir / "demo.proto").exists()
