"""Known-BROKEN reference PaymentService (test fixture, M-T2.3).

Plausible-but-wrong: it returns a transaction for ANY card — no Luhn check, no expiry check. A
static analyzer sees a complete Charge implementation (the saturation problem); only *behavior*
catches it. Used to prove the suite fails the validation RPCs while still passing the happy path.
"""
import os
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc


class PaymentService(demo_pb2_grpc.PaymentServiceServicer):
    def Charge(self, request, context):
        # No validation at all — accepts every card, including invalid/expired ones.
        return demo_pb2.ChargeResponse(transaction_id="txn-broken-9999")


def serve():
    port = os.environ.get("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_PaymentServiceServicer_to_server(PaymentService(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
