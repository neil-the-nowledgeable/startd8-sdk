"""Known-GOOD reference server for the P2 stateless services (Currency/Shipping/Ad).

Correct enough to satisfy every invariant the P2 suites assert. Run as a subprocess with PORT; the
demo_pb2/demo_pb2_grpc stubs are copied alongside it.
"""
import os
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc

_KNOWN = {"USD", "EUR", "GBP", "JPY", "CAD"}


class Currency(demo_pb2_grpc.CurrencyServiceServicer):
    def Convert(self, request, context):
        src = getattr(request, "from")
        if request.to_code not in _KNOWN:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "unknown currency")
        # identity + deterministic (fixed 1:1 for the fixture — invariants don't need real rates).
        return demo_pb2.Money(currency_code=request.to_code, units=src.units, nanos=src.nanos)

    def GetSupportedCurrencies(self, request, context):
        return demo_pb2.GetSupportedCurrenciesResponse(currency_codes=sorted(_KNOWN))


class Shipping(demo_pb2_grpc.ShippingServiceServicer):
    def GetQuote(self, request, context):
        return demo_pb2.GetQuoteResponse(cost_usd=demo_pb2.Money(currency_code="USD", units=8, nanos=990000000))


class Ad(demo_pb2_grpc.AdServiceServicer):
    def GetAds(self, request, context):
        return demo_pb2.AdResponse(ads=[demo_pb2.Ad(redirect_url="/product/OLJCESPC7Z", text="Buy now!")])


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
