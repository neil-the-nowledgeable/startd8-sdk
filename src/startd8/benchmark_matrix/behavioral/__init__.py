"""Behavioral (executed) functional-correctness scoring — Track 2 (M-T2.2 / M-T2.3).

The discriminating signal Round 1 lacks: run the generated service and check it *behaves*.
- ``contract`` — startup contract + per-language serve resolution (how to launch a service).
- ``charge_suite`` — the SDK-authored paymentservice.Charge ground-truth gRPC suite.
- ``demo_pb2`` / ``demo_pb2_grpc`` — vendored stubs generated from the benchmark ``demo.proto``.
- ``resolved_pricing_suite`` — canonical OpenAI/Codex audit seed behavioral suite adapter.

The sandbox primitive that hosts a service (``run_service_sandboxed``) lives in ``..sandbox``.
"""
from .contract import StartupContract, resolve_serve_command
from .charge_suite import RpcResult, SuiteResult, run_charge_suite, SUITE_VERSION
from .catalog_suite import run_catalog_suite
from .currency_suite import run_currency_suite
from .shipping_suite import run_shipping_suite
from .ad_suite import run_ad_suite
from .resolved_pricing_suite import run_resolved_pricing_suite
from .execute import BehavioralResult, run_behavioral_cell

__all__ = [
    "StartupContract",
    "resolve_serve_command",
    "RpcResult",
    "SuiteResult",
    "run_charge_suite",
    "run_catalog_suite",
    "run_currency_suite",
    "run_shipping_suite",
    "run_ad_suite",
    "run_resolved_pricing_suite",
    "SUITE_VERSION",
    "BehavioralResult",
    "run_behavioral_cell",
]
