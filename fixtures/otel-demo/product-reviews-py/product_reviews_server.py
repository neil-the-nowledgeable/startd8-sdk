#!/usr/bin/env python3
"""ProductReviewService with GenAI RPC (Step 5 — llm merge)."""
from __future__ import annotations

import json
import os
import sys
from concurrent import futures
from pathlib import Path

import grpc
import openai
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

_PROTO = Path(__file__).resolve().parents[1] / "_proto"
if str(_PROTO) not in sys.path:
    sys.path.insert(0, str(_PROTO))

import demo_pb2  # noqa: E402
import demo_pb2_grpc  # noqa: E402

SUMMARIES_PATH = Path(__file__).with_name("product-review-summaries.json")


def _load_summaries() -> dict[str, str]:
    if not SUMMARIES_PATH.is_file():
        return {}
    data = json.loads(SUMMARIES_PATH.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in data.get("product-review-summaries", []):
        pid = row.get("product_id")
        if pid:
            out[pid] = row.get("product_review_summary", "")
    return out


class ProductReviewService(demo_pb2_grpc.ProductReviewServiceServicer):
    def __init__(self) -> None:
        self._summaries = _load_summaries()

    def GetProductReviews(self, request, context):
        resp = demo_pb2.GetProductReviewsResponse()
        resp.product_id = request.product_id
        return resp

    def GetAverageProductReviewScore(self, request, context):
        return demo_pb2.GetAverageProductReviewScoreResponse(score=4.2)

    def AskProductAIAssistant(self, request, context):
        product_id = request.product_id
        summary = self._summaries.get(product_id, "")
        if not summary and os.environ.get("OPENAI_API_KEY"):
            client = openai.OpenAI()
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": f"Summarize reviews for product {product_id}"},
                ],
                max_tokens=120,
            )
            summary = completion.choices[0].message.content or summary
        return demo_pb2.AskProductAIAssistantResponse(summary=summary)


def serve() -> None:
    api.set_provider(FlagdProvider())
    port = os.environ.get("PRODUCT_REVIEWS_PORT", "3551")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    demo_pb2_grpc.add_ProductReviewServiceServicer_to_server(ProductReviewService(), server)
    server.add_insecure_port(f"0.0.0.0:{port}")
    server.start()
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
