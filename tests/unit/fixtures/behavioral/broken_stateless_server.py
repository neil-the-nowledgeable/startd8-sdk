"""Known-BROKEN reference server for the P2 stateless services.

Plausible-but-wrong: each service violates the suite's invariants in a way a static/compile check
can't see — used to prove the suites DISCRIMINATE (broken coverage < 1.0).
"""
import os
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc


class Currency(demo_pb2_grpc.CurrencyServiceServicer):
    def Convert(self, request, context):
        src = getattr(request, "from")
        # No validation (accepts any to_code) AND identity broken (doubles the amount).
        return demo_pb2.Money(currency_code=request.to_code, units=src.units * 2, nanos=src.nanos)

    def GetSupportedCurrencies(self, request, context):
        return demo_pb2.GetSupportedCurrenciesResponse(currency_codes=[])  # empty


class Shipping(demo_pb2_grpc.ShippingServiceServicer):
    def GetQuote(self, request, context):
        # Negative cost + invalid 2-letter currency code.
        return demo_pb2.GetQuoteResponse(cost_usd=demo_pb2.Money(currency_code="US", units=-5, nanos=0))


class Ad(demo_pb2_grpc.AdServiceServicer):
    def GetAds(self, request, context):
        return demo_pb2.AdResponse(ads=[])  # no ads


def serve():
    port = os.environ.get("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    demo_pb2_grpc.add_CurrencyServiceServicer_to_server(Currency(), server)
    demo_pb2_grpc.add_ShippingServiceServicer_to_server(Shipping(), server)
    demo_pb2_grpc.add_AdServiceServicer_to_server(Ad(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
