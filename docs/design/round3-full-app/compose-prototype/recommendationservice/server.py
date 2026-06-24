"""PROTOTYPE — recommendationservice for the Round 3 docker-compose FLEET substrate prototype.

This is the recommendation_reference fixture (tests/.../fixtures/recommendation_reference/server.py),
unchanged in behavior: ListRecommendations dials the productcatalog peer at
PRODUCT_CATALOG_SERVICE_ADDR (a real container, reached by compose service-DNS), calls ListProducts
to learn the catalog, and returns recommended ids drawn FROM the catalog EXCLUDING the request inputs.

The gRPC stubs (demo_pb2 / demo_pb2_grpc) are co-located into this server's cwd by the image build
(COPY from behavioral/), exactly as the test stager co-locates them in the in-process harness.
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
        catalog = self._catalog.ListProducts(demo_pb2.Empty(), timeout=5.0)
        catalog_ids = [p.id for p in catalog.products]
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
    print(f"recommendationservice listening on {port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
