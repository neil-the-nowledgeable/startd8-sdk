# OTel Demo — Python Capability Index Coverage

**Corpus:** `otel-demo-python+fixtures`  
**Workdir:** `/private/tmp/otel-demo-proto-fetch+/Users/neilyashinsky/Documents/dev/startd8-otel-python-rebuild/fixtures/otel-demo`  
**Files analyzed:** 34 (skipped generated: 6, parse errors: 0)  
**Overall index coverage:** **70.6%** (mean of four dimensions)

## Dimension breakdown

| Dimension | Detected | Total | Coverage |
| --- | ---: | ---: | ---: |
| communication_patterns | 7 | 15 | 46.7% |
| ast_nodes | 75 | 132 | 56.8% |
| language_composites | 9 | 10 | 90.0% |
| manifest_kinds | 8 | 9 | 88.9% |

## OTel §5 patterns detected (union)

- `PY-OTEL-5.1-DNS`
- `PY-OTEL-5.1-HTTP`
- `PY-OTEL-5.3-RPC`
- `PY-OTEL-5.4-MESSAGING`
- `PY-OTEL-5.5-DATABASE`
- `PY-OTEL-5.6-FEATURE-FLAGS`
- `PY-OTEL-5.6-GENAI`

## Patterns not evidenced in Python sources

- `PY-OTEL-5.2-HTTP-METRICS`
- `PY-OTEL-5.3-CONNECT`
- `PY-OTEL-5.6-GRAPHQL`
- `PY-OTEL-5.6-FAAS`
- `PY-OTEL-5.7-CICD`
- `PY-OTEL-5.7-CLI`
- `PY-OTEL-5.1-OBJECT-STORE`
- `PY-OTEL-5.1-CLOUD-SDK`

## Per-file hyp(f)

- `src/llm/app.py` (223 lines) — **hyp:** PY-OTEL-5.1-HTTP, PY-OTEL-5.6-FEATURE-FLAGS; manifest: function, variable
- `src/load-generator/locustfile.py` (285 lines) — **hyp:** PY-OTEL-5.1-HTTP, PY-OTEL-5.3-RPC, PY-OTEL-5.6-FEATURE-FLAGS; manifest: async_function, async_method, class, function, method, variable
- `src/product-reviews/database.py` (91 lines) — **hyp:** PY-OTEL-5.5-DATABASE; manifest: function, variable
- `src/product-reviews/demo_pb2.py` — *skipped (generated protobuf)*
- `src/product-reviews/demo_pb2_grpc.py` — *skipped (generated protobuf)*
- `src/product-reviews/metrics.py` (24 lines) — **hyp:** ∅; manifest: function, variable
- `src/product-reviews/product_reviews_server.py` (385 lines) — **hyp:** PY-OTEL-5.3-RPC, PY-OTEL-5.6-FEATURE-FLAGS, PY-OTEL-5.6-GENAI; manifest: class, function, method, variable
- `src/recommendation/demo_pb2.py` — *skipped (generated protobuf)*
- `src/recommendation/demo_pb2_grpc.py` — *skipped (generated protobuf)*
- `src/recommendation/logger.py` (29 lines) — **hyp:** ∅; manifest: class, function, method, variable
- `src/recommendation/metrics.py` (18 lines) — **hyp:** ∅; manifest: function, variable
- `src/recommendation/recommendation_server.py` (174 lines) — **hyp:** PY-OTEL-5.3-RPC, PY-OTEL-5.6-FEATURE-FLAGS; manifest: class, function, method, variable
- `_proto/demo_pb2.py` — *skipped (generated protobuf)*
- `_proto/demo_pb2_grpc.py` — *skipped (generated protobuf)*
- `accounting-py/consumer.py` (89 lines) — **hyp:** PY-OTEL-5.4-MESSAGING, PY-OTEL-5.1-DNS; manifest: constant, function, variable
- `accounting-py/models.py` (55 lines) — **hyp:** PY-OTEL-5.5-DATABASE; manifest: class, function, type_alias, variable
- `cart-py/cart_server.py` (57 lines) — **hyp:** PY-OTEL-5.3-RPC, PY-OTEL-5.6-FEATURE-FLAGS, PY-OTEL-5.1-DNS; manifest: class, constant, function, method, variable
- `cart-py/valkey_store.py` (39 lines) — **hyp:** PY-OTEL-5.1-HTTP, PY-OTEL-5.4-MESSAGING, PY-OTEL-5.5-DATABASE; manifest: class, method, variable
- `checkout-kafka-py/producer.py` (49 lines) — **hyp:** PY-OTEL-5.4-MESSAGING, PY-OTEL-5.1-DNS; manifest: constant, function, variable
- `email-py/app/__init__.py` (0 lines) — **hyp:** ∅; manifest: —
- `email-py/app/ai_schemas.py` (23 lines) — **hyp:** ∅; manifest: constant, function, type_alias
- `email-py/app/completeness.py` (30 lines) — **hyp:** ∅; manifest: class, constant, function, type_alias, variable
- `email-py/app/db.py` (83 lines) — **hyp:** PY-OTEL-5.5-DATABASE; manifest: constant, function, variable
- `email-py/app/export.py` (32 lines) — **hyp:** ∅; manifest: constant, function, type_alias, variable
- `email-py/app/health.py` (36 lines) — **hyp:** PY-OTEL-5.1-HTTP, PY-OTEL-5.5-DATABASE; manifest: function, variable
- `email-py/app/main.py` (100 lines) — **hyp:** PY-OTEL-5.1-HTTP; manifest: async_function, variable
- `email-py/app/models.py` (18 lines) — **hyp:** ∅; manifest: class, type_alias, variable
- `email-py/app/openapi_contract.py` (271 lines) — **hyp:** ∅; manifest: constant, function, type_alias
- `email-py/app/routers.py` (66 lines) — **hyp:** PY-OTEL-5.1-HTTP; manifest: function, variable
- `email-py/app/tables.py` (44 lines) — **hyp:** ∅; manifest: class, function, type_alias, variable
- `email-py/app/web.py` (152 lines) — **hyp:** PY-OTEL-5.1-HTTP; manifest: async_function, function, variable
- `email-py/clients/__init__.py` (0 lines) — **hyp:** ∅; manifest: —
- `email-py/clients/http_client.py` (66 lines) — **hyp:** PY-OTEL-5.1-HTTP; manifest: class, method, variable
- `email-py/tests/test_completeness.py` (24 lines) — **hyp:** PY-OTEL-5.1-DNS; manifest: function, variable
- `email-py/tests/test_contract.py` (28 lines) — **hyp:** PY-OTEL-5.1-DNS; manifest: function, variable
- `email-py/tests/test_health.py` (33 lines) — **hyp:** PY-OTEL-5.1-DNS; manifest: function, variable
- `email-py/tests/test_openapi_contract.py` (84 lines) — **hyp:** PY-OTEL-5.1-HTTP, PY-OTEL-5.1-DNS; manifest: constant, function, type_alias, variable
- `email-py/tests/test_route_smoke.py` (234 lines) — **hyp:** PY-OTEL-5.1-HTTP, PY-OTEL-5.5-DATABASE, PY-OTEL-5.1-DNS; manifest: constant, function, variable
- `payment-py/payment_server.py` (65 lines) — **hyp:** PY-OTEL-5.3-RPC, PY-OTEL-5.6-FEATURE-FLAGS, PY-OTEL-5.1-DNS; manifest: class, constant, function, method, variable
- `product-reviews-py/product_reviews_server.py` (78 lines) — **hyp:** PY-OTEL-5.3-RPC, PY-OTEL-5.6-FEATURE-FLAGS, PY-OTEL-5.6-GENAI, PY-OTEL-5.1-DNS; manifest: class, constant, function, method, type_alias, variable

## Interpretation

- **communication_patterns** — share of `PY-OTEL-5.*` crosswalk entries with static import/call/decorator evidence (landscape §5).
- **ast_nodes** — share of catalogued `PY-AST-*` node types appearing anywhere in the corpus.
- **language_composites** — share of `PY-LC-*` composites evidenced.
- **manifest_kinds** — share of `PY-MAN-*` ElementKind values extractable from AST.

Generated by `scripts/analyze_otel_demo_python_coverage.py`.
