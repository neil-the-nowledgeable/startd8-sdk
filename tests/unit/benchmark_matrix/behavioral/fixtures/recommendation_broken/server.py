"""DELIBERATELY-BROKEN RecommendationService — proves the recommendation suite DISCRIMINATES.

Two defects in one, mirroring the two oracle axes:

  - it NEVER dials productcatalog (no ``ListProducts`` call) — so the harness call-counter for
    ``PRODUCT_CATALOG_SERVICE_ADDR`` stays 0 (the catalog-dialed gate fails every case); and
  - it echoes the request's INPUT ``product_ids`` straight back — violating exclude-input.

A service that returns hardcoded / echoed ids without calling the catalog must get ZERO credit
(every case is gated on ``catalog_dialed``), so all three cases fail. This is the recommendation
analogue of checkout's "never dials payment" broken fixture.
"""
from __future__ import annotations

import os
from concurrent import futures

import grpc

import demo_pb2
import demo_pb2_grpc


class RecommendationService(demo_pb2_grpc.RecommendationServiceServicer):
    def ListRecommendations(self, request, context):
        # BUG: never dials productcatalog; just echoes the inputs back as "recommendations".
        return demo_pb2.ListRecommendationsResponse(product_ids=list(request.product_ids))


def main() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_RecommendationServiceServicer_to_server(RecommendationService(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    main()
