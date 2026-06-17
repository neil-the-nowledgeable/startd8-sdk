"""Careless-but-happy-path CurrencyService reference server (hardened-tier discrimination fixture).

Correct on every BASELINE invariant (USD→USD identity, rejects unknown code, deterministic, non-empty
supported list) but CARELESS on precision: it integer-truncates conversions to whole units and ignores
sub-unit (`nanos`) input. A truncating impl round-trips lossily, so it PASSES the baseline currency
suite (1.0) yet FAILS the hardened round-trip invariant (<1.0) — exactly the flagship/mid-tier signal
the hardened tier is meant to expose. Hermetic: grpcio + Python only.
"""
import os
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc

# Deliberately includes a fractional rate (EUR) so truncation loses precision and round-trip drifts.
_RATES = {"USD": 1.0, "EUR": 0.123, "GBP": 0.8, "JPY": 110.0, "CAD": 1.35}


class Currency(demo_pb2_grpc.CurrencyServiceServicer):
    def Convert(self, request, context):
        src = getattr(request, "from")
        if request.to_code not in _RATES or src.currency_code not in _RATES:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "unknown currency")
        # CARELESS: drop src.nanos, integer-truncate to whole units (no sub-unit precision).
        usd = src.units / _RATES[src.currency_code]
        out_units = int(usd * _RATES[request.to_code])  # truncates toward zero
        return demo_pb2.Money(currency_code=request.to_code, units=out_units, nanos=0)

    def GetSupportedCurrencies(self, request, context):
        return demo_pb2.GetSupportedCurrenciesResponse(currency_codes=sorted(_RATES))


def serve():
    port = os.environ.get("PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    demo_pb2_grpc.add_CurrencyServiceServicer_to_server(Currency(), server)
    server.add_insecure_port(f"127.0.0.1:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
