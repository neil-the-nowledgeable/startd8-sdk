"""Behavioral (executed) functional-correctness scoring — Track 2 (M-T2.2 / M-T2.3).

The discriminating signal Round 1 lacks: run the generated service and check it *behaves*.
- ``contract`` — startup contract + per-language serve resolution (how to launch a service).
- ``charge_suite`` — the SDK-authored paymentservice.Charge ground-truth gRPC suite.
- ``demo_pb2`` / ``demo_pb2_grpc`` — vendored stubs generated from the benchmark ``demo.proto``.

The sandbox primitive that hosts a service (``run_service_sandboxed``) lives in ``..sandbox``.
"""
from .contract import StartupContract, resolve_serve_command
from .charge_suite import RpcResult, SuiteResult, run_charge_suite, SUITE_VERSION
from .execute import BehavioralResult, run_behavioral_cell

__all__ = [
    "StartupContract",
    "resolve_serve_command",
    "RpcResult",
    "SuiteResult",
    "run_charge_suite",
    "SUITE_VERSION",
    "BehavioralResult",
    "run_behavioral_cell",
]
