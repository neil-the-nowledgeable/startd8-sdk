"""Known-GOOD reference PaymentService (test fixture, M-T2.3).

A correct Charge: Luhn-validates the card number and rejects expired cards. Used to prove the
behavioral suite passes a correct implementation. Run as a standalone subprocess inside the
sandbox; the demo_pb2/demo_pb2_grpc stubs are copied alongside it (imported flat from cwd).
"""
import datetime
import os
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
        card = request.credit_card
        if not _luhn_ok(card.credit_card_number):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid credit card")
        today = datetime.date.today()
        if (card.credit_card_expiration_year, card.credit_card_expiration_month) < (today.year, today.month):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "expired credit card")
        return demo_pb2.ChargeResponse(transaction_id="txn-reference-0001")


def serve():
    port = os.environ.get("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
