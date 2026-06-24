"""CORRECT reference RecommendationService — the known-good oracle for the recommendation suite.

A standalone Python gRPC server launched by the Python startup contract
(``cd src/recommendationservice && exec python3 server.py`` with ``$PORT`` in the env). It implements
``ListRecommendations`` with the real Online Boutique semantics the suite asserts:

  - dial the productcatalog peer at ``PRODUCT_CATALOG_SERVICE_ADDR`` and call ``ListProducts`` to
    learn the full catalog (this is the dependency call the harness counts);
  - return a few recommended product ids drawn FROM that catalog, EXCLUDING the request's input
    ``product_ids`` — so a recommendation never echoes its own inputs and never invents ids.

The gRPC stubs (``demo_pb2`` / ``demo_pb2_grpc``) are co-located into this server's cwd by the test
stager (the demo_pb2_grpc co-located-import convention, mirroring the email/checkout fixtures).
"""
from __future__ import annotations

import os
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc

_MAX_RECOMMENDATIONS = 4


class RecommendationService(demo_pb2_grpc.RecommendationServiceServicer):
    def __init__(self) -> None:
        addr = os.environ["PRODUCT_CATALOG_SERVICE_ADDR"]
        self._catalog_channel = grpc.insecure_channel(addr)
        self._catalog = demo_pb2_grpc.ProductCatalogServiceStub(self._catalog_channel)

    def ListRecommendations(self, request, context):
        # Dial productcatalog (the counted dependency call) to learn the catalog universe.
        catalog = self._catalog.ListProducts(demo_pb2.Empty(), timeout=5.0)
        catalog_ids = [p.id for p in catalog.products]
        # Recommend ids FROM the catalog EXCLUDING the request's inputs.
        inputs = set(request.product_ids)
        candidates = [pid for pid in catalog_ids if pid not in inputs]
        recommended = candidates[:_MAX_RECOMMENDATIONS]
        return demo_pb2.ListRecommendationsResponse(product_ids=recommended)


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_RecommendationServiceServicer_to_server(RecommendationService(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()
