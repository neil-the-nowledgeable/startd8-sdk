"""paymentservice.Charge behavioral ground-truth suite (M-T2.3 / FR-T2-SUITE / FR-T2-PROV).

SDK-authored, language-agnostic over the gRPC wire — it talks to a live PaymentService on
``127.0.0.1:<port>`` regardless of what language the server was generated in. It asserts the
``Charge`` contract's *behavior*, which is what discriminates frontier models (static coverage
saturates):

  - Luhn-valid card + future expiry  → a non-empty ``transaction_id``
  - invalid-Luhn card                → the RPC is rejected (gRPC error), not a transaction
  - expired card                     → the RPC is rejected (gRPC error)

``coverage`` ∈ [0,1] = passing RPCs / total; provenance carries the suite version + per-RPC results.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import grpc

from . import demo_pb2, demo_pb2_grpc

SUITE_VERSION = "charge-suite/1"

# Classic Visa test PAN (Luhn-valid) and the same with the check digit flipped (Luhn-invalid).
_VALID_PAN = "4111111111111111"
_INVALID_PAN = "4111111111111112"


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


def _money(units: int = 10, nanos: int = 0, code: str = "USD"):
    return demo_pb2.Money(currency_code=code, units=units, nanos=nanos)


def _card(number: str, cvv: int = 123, year: int = 2030, month: int = 12):
    return demo_pb2.CreditCardInfo(
        credit_card_number=number, credit_card_cvv=cvv,
        credit_card_expiration_year=year, credit_card_expiration_month=month,
    )


def _charge(stub, *, number: str, year: int, timeout: float = 5.0):
    req = demo_pb2.ChargeRequest(amount=_money(), credit_card=_card(number, year=year))
    return stub.Charge(req, timeout=timeout)


def run_charge_suite(port: int, *, host: str = "127.0.0.1", connect_timeout: float = 5.0) -> SuiteResult:
    """Connect to a live PaymentService and run the Charge ground-truth checks (the client window)."""
    suite = SuiteResult(suite_version=SUITE_VERSION)
    try:
        channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(channel).result(timeout=connect_timeout)
    except Exception as e:  # noqa: BLE001 — failure to connect is an env outcome (degrade upstream)
        suite.connect_error = f"{type(e).__name__}: {e}"
        return suite
    try:
        stub = demo_pb2_grpc.PaymentServiceStub(channel)

        # 1) Valid card → non-empty transaction_id.
        try:
            resp = _charge(stub, number=_VALID_PAN, year=2030)
            ok = bool(getattr(resp, "transaction_id", ""))
            suite.results.append(RpcResult("charge_valid_card", ok,
                                           "transaction_id set" if ok else "empty transaction_id"))
        except grpc.RpcError as e:
            suite.results.append(RpcResult("charge_valid_card", False, f"unexpected error: {e.code()}"))

        # 2) Invalid-Luhn card → must be rejected.
        try:
            _charge(stub, number=_INVALID_PAN, year=2030)
            suite.results.append(RpcResult("charge_invalid_card_rejected", False, "accepted an invalid card"))
        except grpc.RpcError:
            suite.results.append(RpcResult("charge_invalid_card_rejected", True, "rejected as expected"))

        # 3) Expired card → must be rejected.
        try:
            _charge(stub, number=_VALID_PAN, year=2000)
            suite.results.append(RpcResult("charge_expired_card_rejected", False, "accepted an expired card"))
        except grpc.RpcError:
            suite.results.append(RpcResult("charge_expired_card_rejected", True, "rejected as expected"))
    finally:
        channel.close()
    return suite
