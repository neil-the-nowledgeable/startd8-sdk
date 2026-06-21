"""ResolvedPriceService.AssessLines behavioral suite adapter.

The canonical S2 suite is stored as data under docs/design/benchmark-bias-audit. This module adapts
those RPC-shaped fixtures to a live gRPC service and reports the same SuiteResult shape as the other
Track 2 behavioral suites.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import grpc

from . import resolved_pricing_pb2 as pb
from . import resolved_pricing_pb2_grpc

SUITE_VERSION = "resolved-pricing-suite/1"
_CASE_MODULE = None


@dataclass
class RpcResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class SuiteResult:
    suite_version: str
    results: List[RpcResult] = field(default_factory=list)
    connect_error: str = ""

    @property
    def coverage(self) -> float:
        return (sum(1 for r in self.results if r.passed) / len(self.results)) if self.results else 0.0

    def to_dict(self) -> dict:
        return {
            "suite_version": self.suite_version,
            "coverage": self.coverage,
            "connect_error": self.connect_error,
            "results": [r.__dict__ for r in self.results],
        }


def _case_module():
    global _CASE_MODULE
    if _CASE_MODULE is not None:
        return _CASE_MODULE
    repo = Path(__file__).resolve().parents[4]
    path = repo / "docs/design/benchmark-bias-audit/bias_audit_openai/runs/s2-codex-suite-clean-20260618T215301Z/suite.py"
    if not path.is_file():
        raise FileNotFoundError(f"resolved pricing suite artifact not found: {path}")
    spec = importlib.util.spec_from_file_location("resolved_pricing_cases", path)
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old
    _CASE_MODULE = module
    return module


def _enum(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    return getattr(pb, value)


def _set_amount(message, data: dict[str, Any]) -> None:
    message.decimal = data["decimal"]


def request_from_dict(data: dict[str, Any]) -> pb.AssessLinesRequest:
    request = pb.AssessLinesRequest()
    if "currency_code" in data:
        request.currency_code = data["currency_code"]
    if "currency_scale" in data:
        request.currency_scale = data["currency_scale"]
    request.rounding_mode = _enum(data.get("rounding_mode"), pb.ROUNDING_MODE_UNSPECIFIED)
    request.discount_strategy = _enum(
        data.get("discount_strategy"), pb.DISCOUNT_STRATEGY_UNSPECIFIED
    )
    for line_data in data.get("lines", []):
        line = request.lines.add()
        if "line_key" in line_data:
            line.line_key = line_data["line_key"]
        if "quantity" in line_data:
            line.quantity = line_data["quantity"]
        if "unit_amount" in line_data:
            _set_amount(line.unit_amount, line_data["unit_amount"])
        if "comparison_unit_amount" in line_data:
            _set_amount(line.comparison_unit_amount, line_data["comparison_unit_amount"])
        if "candidate_unit_amount" in line_data:
            _set_amount(line.candidate_unit_amount, line_data["candidate_unit_amount"])
        if "price_on_request" in line_data:
            line.price_on_request = line_data["price_on_request"]
        for reduction_data in line_data.get("reductions", []):
            reduction = line.reductions.add()
            reduction.kind = _enum(reduction_data.get("kind"), pb.REDUCTION_KIND_UNSPECIFIED)
            reduction.percent_levels.extend(reduction_data.get("percent_levels", []))
            if "amount" in reduction_data:
                _set_amount(reduction.amount, reduction_data["amount"])
    return request


def response_from_dict(data: dict[str, Any]) -> pb.AssessLinesResponse:
    response = pb.AssessLinesResponse(currency_code=data.get("currency_code", ""))
    for line_data in data.get("lines", []):
        line = response.lines.add()
        line.line_key = line_data.get("line_key", "")
        line.quantity = line_data.get("quantity", "")
        line.price_on_request = bool(line_data.get("price_on_request", False))
        if "comparison_unit_amount" in line_data:
            _set_amount(line.comparison_unit_amount, line_data["comparison_unit_amount"])
        if "selected_unit_amount" in line_data:
            _set_amount(line.selected_unit_amount, line_data["selected_unit_amount"])
        if "promotion_applied" in line_data:
            line.promotion_applied = bool(line_data["promotion_applied"])
        if "line_base_amount" in line_data:
            _set_amount(line.line_base_amount, line_data["line_base_amount"])
        if "reduction" in line_data:
            reduction_data = line_data["reduction"]
            if "amount" in reduction_data:
                _set_amount(line.reduction.amount, reduction_data["amount"])
            line.reduction.percent_total = reduction_data.get("percent_total", "")
            line.reduction.percent_levels.extend(reduction_data.get("percent_levels", []))
        if "line_due_amount" in line_data:
            _set_amount(line.line_due_amount, line_data["line_due_amount"])
    totals_data = data.get("totals")
    if totals_data is not None:
        if "base_amount" in totals_data:
            _set_amount(response.totals.base_amount, totals_data["base_amount"])
        if "reduction_amount" in totals_data:
            _set_amount(response.totals.reduction_amount, totals_data["reduction_amount"])
        if "due_amount" in totals_data:
            _set_amount(response.totals.due_amount, totals_data["due_amount"])
        response.totals.price_on_request_count = totals_data.get("price_on_request_count", 0)
    return response


def _has(message, field: str) -> bool:
    try:
        return message.HasField(field)
    except ValueError:
        return False


def _amount_to_dict(message) -> dict[str, str]:
    return {"decimal": message.decimal}


def response_to_dict(response: pb.AssessLinesResponse) -> dict[str, Any]:
    data: dict[str, Any] = {"currency_code": response.currency_code, "lines": []}
    for line in response.lines:
        line_data: dict[str, Any] = {
            "line_key": line.line_key,
            "quantity": line.quantity,
            "price_on_request": line.price_on_request,
        }
        if _has(line, "comparison_unit_amount"):
            line_data["comparison_unit_amount"] = _amount_to_dict(line.comparison_unit_amount)
        if _has(line, "selected_unit_amount"):
            line_data["selected_unit_amount"] = _amount_to_dict(line.selected_unit_amount)
        if not line.price_on_request or line.promotion_applied:
            line_data["promotion_applied"] = line.promotion_applied
        if _has(line, "line_base_amount"):
            line_data["line_base_amount"] = _amount_to_dict(line.line_base_amount)
        if _has(line, "reduction"):
            reduction: dict[str, Any] = {
                "percent_total": line.reduction.percent_total,
                "percent_levels": list(line.reduction.percent_levels),
            }
            if _has(line.reduction, "amount"):
                reduction["amount"] = _amount_to_dict(line.reduction.amount)
            line_data["reduction"] = reduction
        if _has(line, "line_due_amount"):
            line_data["line_due_amount"] = _amount_to_dict(line.line_due_amount)
        data["lines"].append(line_data)
    if _has(response, "totals"):
        totals: dict[str, Any] = {
            "price_on_request_count": response.totals.price_on_request_count,
        }
        if _has(response.totals, "base_amount"):
            totals["base_amount"] = _amount_to_dict(response.totals.base_amount)
        if _has(response.totals, "reduction_amount"):
            totals["reduction_amount"] = _amount_to_dict(response.totals.reduction_amount)
        if _has(response.totals, "due_amount"):
            totals["due_amount"] = _amount_to_dict(response.totals.due_amount)
        data["totals"] = totals
    return data


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def _compare_response(actual: pb.AssessLinesResponse, expected: dict[str, Any]) -> tuple[bool, str]:
    actual_data = response_to_dict(actual)
    if actual_data == expected:
        return True, "matched"
    return False, f"actual={_json(actual_data)} expected={_json(expected)}"


def run_resolved_pricing_suite(
    port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0
) -> SuiteResult:
    """Connect to a live ResolvedPriceService and run canonical S2 behavioral cases."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        cases = _case_module()
    except Exception as exc:  # noqa: BLE001 - missing suite data is an environment outcome
        suite.connect_error = f"{type(exc).__name__}: {exc}"
        return suite

    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as exc:  # noqa: BLE001 - failure to connect is an environment outcome
        suite.connect_error = f"{type(exc).__name__}: {exc}"
        return suite

    stub = resolved_pricing_pb2_grpc.ResolvedPriceServiceStub(channel)

    try:
        for case in cases.VALID_CASES:
            name = case["name"]
            try:
                response = stub.AssessLines(request_from_dict(case["request"]), timeout=5.0)
                suite.results.append(
                    RpcResult(name, *_compare_response(response, case["expected_response"]))
                )
            except grpc.RpcError as exc:
                suite.results.append(RpcResult(name, False, f"unexpected RPC error: {exc.code()}"))
            except Exception as exc:  # noqa: BLE001
                suite.results.append(RpcResult(name, False, f"{type(exc).__name__}: {exc}"))

        for case in cases.INVALID_CASES:
            name = case["name"]
            try:
                request = request_from_dict(case["request"])
            except Exception as exc:  # noqa: BLE001
                suite.results.append(
                    RpcResult(name, True, f"client-side protobuf rejection: {type(exc).__name__}")
                )
                continue
            try:
                stub.AssessLines(request, timeout=5.0)
                suite.results.append(RpcResult(name, False, "accepted an invalid request"))
            except grpc.RpcError as exc:
                good = exc.code() == grpc.StatusCode.INVALID_ARGUMENT
                suite.results.append(
                    RpcResult(
                        name,
                        good,
                        "INVALID_ARGUMENT" if good else f"wrong code {exc.code()}",
                    )
                )
            except Exception as exc:  # noqa: BLE001
                suite.results.append(RpcResult(name, False, f"{type(exc).__name__}: {exc}"))
    finally:
        channel.close()
    return suite
