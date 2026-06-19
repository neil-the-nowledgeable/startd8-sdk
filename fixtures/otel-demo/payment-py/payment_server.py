#!/usr/bin/env python3
"""PaymentService.Charge — Python port of payment/charge.js (Step 6)."""
from __future__ import annotations

import os
import sys
import uuid
from concurrent import futures
from datetime import datetime
from pathlib import Path

import grpc
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

_PROTO = Path(__file__).resolve().parents[1] / "_proto"
if str(_PROTO) not in sys.path:
    sys.path.insert(0, str(_PROTO))

import demo_pb2  # noqa: E402
import demo_pb2_grpc  # noqa: E402

LOYALTY_LEVELS = ("platinum", "gold", "silver", "bronze")


def _valid_card(number: str) -> tuple[bool, str]:
    digits = number.replace(" ", "")
    if not digits.isdigit() or len(digits) < 13:
        return False, "unknown"
    if digits.startswith("4"):
        return True, "visa"
    if digits.startswith("5"):
        return True, "mastercard"
    return False, "unknown"


class PaymentService(demo_pb2_grpc.PaymentServiceServicer):
    def Charge(self, request, context):
        failure_rate = int(api.get_client().get_number_value("paymentFailure", 0))
        card = request.credit_card
        valid, card_type = _valid_card(card.credit_card_number)
        if not valid or card_type not in ("visa", "mastercard"):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid card")
        now = datetime.utcnow()
        exp_ok = (now.year, now.month) <= (card.credit_card_expiration_year, card.credit_card_expiration_month)
        if not exp_ok:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "card expired")
        if failure_rate > 0:
            context.abort(grpc.StatusCode.INTERNAL, "paymentFailure flag")
        return demo_pb2.ChargeResponse(transaction_id=str(uuid.uuid4()))


def serve() -> None:
    api.set_provider(FlagdProvider())
    port = os.environ.get("PAYMENT_PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
