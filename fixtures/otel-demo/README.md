# OTel Demo — Python reference ports (Steps 1–6)

SDK-owned Python ports of non-Python OTel Demo services for capability-index coverage,
Prime Contractor seeds, and Plan Ingestion import-pattern handoff.

**Upstream reference:** `open-telemetry/opentelemetry-demo` tag **2.2.0** (read-only; not modified).

| Fixture | Step | Source service | Language | Patterns |
| --- | ---: | --- | --- | --- |
| `accounting-py/` | 1 | accounting | C# | Kafka consumer, SQLAlchemy/Postgres |
| `checkout-kafka-py/` | 2 | checkout (producer slice) | Go | Kafka producer (pattern fixture; no benchmark cell) |
| `email-py/` | 3 | email | Ruby | FastAPI HTTP + OpenFeature + `api.yaml` overlay |
| `cart-py/` | 4 | cart | C# | gRPC CartService + Redis/Valkey |
| `product-reviews-py/` | 5 | product-reviews + llm | Python | GenAI RPC (`AskProductAIAssistant`) |
| `payment-py/` | 6 | payment | Node.js | Leaf gRPC `Charge` (behavioral-eligible seed) |
| `_proto/` | — | shared | — | Generated `demo_pb2` stubs (skipped by resolver) |

## Coverage analysis

```bash
python3 scripts/analyze_otel_demo_python_coverage.py --fixtures-only
python3 scripts/analyze_otel_demo_python_coverage.py   # demo clone + fixtures merged
```

## Requirements

See [OTEL_PYTHON_REBUILD_OPENAPI_REQUIREMENTS.md](../../docs/design/otel-demo-corpus/OTEL_PYTHON_REBUILD_OPENAPI_REQUIREMENTS.md).
