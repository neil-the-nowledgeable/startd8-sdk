"""Hardened-correct reference PaymentService (test fixture).

Satisfies BOTH the baseline charge checks (Luhn + expiry) AND the hardened superset: a UNIQUE
transaction_id per charge (uuid), and validation of amount (non-positive rejected) + card (empty
rejected). Used as the 'good' side of the hardened-charge discrimination test; the existing
good_payment_server.py (constant id, no amount check) is the careless side. Hermetic stdlib + grpcio.
"""
import datetime
import os
import uuid
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc


def _luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()]
    if len(digits) < 12:
        return False
    total, parity = 0, len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class PaymentService(demo_pb2_grpc.PaymentServiceServicer):
    def Charge(self, request, context):
        amt = request.amount
        if amt.units < 0 or (amt.units == 0 and amt.nanos == 0):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "non-positive amount")
        card = request.credit_card
        if not (card.credit_card_number or "").strip():
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "empty card number")
        if not _luhn_ok(card.credit_card_number):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid credit card")
        today = datetime.date.today()
        if (card.credit_card_expiration_year, card.credit_card_expiration_month) < (today.year, today.month):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "expired credit card")
        return demo_pb2.ChargeResponse(transaction_id=f"txn-{uuid.uuid4()}")


def serve():
    port = os.environ.get("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
