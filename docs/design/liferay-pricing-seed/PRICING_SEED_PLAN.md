# Liferay-derived Pricing-Calculator Seed — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-17
**Tracks requirements:** `PRICING_SEED_REQUIREMENTS.md` (drove this plan; updated to v0.2 by it)

This plan maps each requirement to concrete files in `src/startd8/benchmark_matrix/behavioral/` and
`docs/design/model-benchmark/seeds/`, and records what the codebase revealed.

---

## Discoveries (feed the reflection pass)

| What the requirements (v0.1) assumed | What planning revealed |
|---|---|
| **No harness changes** (non-req) | **FALSE.** The behavioral harness is hardcoded to OB's single shared `demo.proto`: `execute.py:_PROTO`, `prepare_node_workdir` (copies `demo.proto` only), committed `demo_pb2.py`/`demo_pb2_grpc.py`/`go_stubs/hipstershop/*`, and references in `contamination.py` + `scoring.py`. A new `PricingService` proto cannot reuse any of it. |
| Suite just plugs into `_SUITES` | True for *registration*, but the suite imports committed stubs `from . import demo_pb2, demo_pb2_grpc`. A pricing suite needs committed `pricing_pb2.py` / `pricing_pb2_grpc.py`, which **do not exist** and have **no generation script** in-repo (stubs are committed artifacts). |
| Proto provisioning is generic | `prepare_node_workdir` hardcodes `_PROTO = demo.proto` and copies only that file. Must be parameterized to provision the seed's proto by name. (Node server loads proto dynamically via `@grpc/proto-loader`, so server-side is fine *once the file is provisioned*.) |
| Money = decimal strings (spike) | House style is `Money{currency_code, units:int64, nanos:int32}` (OB proto). A new proto is a free choice; decimal strings express the rounding spec (FR-7) far better, but this is a deliberate divergence to document. |
| FR-11 contamination = scored probe | `contamination.py` CodeBLEU compares generated code to a **canonical upstream reference**. A *synthetic* pricing service has **no upstream** → the CodeBLEU contamination *score* is N/A. Only the rename/perturbation *hygiene* applies, with low baseline contamination. FR-11 must be reframed. |
| FR-13 scoring needs work | Overspecified — it's free. `scoring.py:300-303` folds `functional` automatically once `run_behavioral_cell` returns coverage; degraded → `missing`, no penalty. Nothing to build. |
| `language_rationale` ≈ "canonical language" | For a synthetic seed there is no canonical upstream language; the field's meaning shifts to "harness-proven offline runtime closure + author-controlled determinism." |

## Step-by-step

**S1 — Author `pricing.proto`** (`benchmark_matrix/behavioral/pricing.proto`). Package
`startd8.bench.pricing.v1`, single `PricingService.PriceCart`, decimal-string money, per the spike
sketch. *Serves FR-1, FR-2, FR-3, FR-5, FR-6, FR-7.*

**S2 — Generate + commit Python stubs** `pricing_pb2.py` / `pricing_pb2_grpc.py` via
`python3 -m grpc_tools.protoc`. Add a one-line gen note to the behavioral README (no gen script
exists today; document the command). *Serves FR-9; resolves D2.*

**S3 — Generalize proto provisioning** (the harness change v0.1 said wouldn't happen). Parameterize
`prepare_node_workdir` (and `_PROTO`) so the proto filename comes from the seed/service rather than
the constant `demo.proto`. Keep `demo.proto` as the default so OB cells are byte-unchanged.
*Resolves D1/D3; additive, ~1 small function signature + call sites.*

**S4 — Write `run_pricing_suite`** (`benchmark_matrix/behavioral/pricing_suite.py`), mirroring
`charge_suite.py`'s `SuiteResult`/`RpcResult` shape, implementing G1–G7. Register in `_SUITES`
(`execute.py`). *Serves FR-9; assertions per spike table.*

**S5 — Author the seed JSON** `docs/design/model-benchmark/seeds/seed-pricingservice.json` with
`service_metadata` (language nodejs, proto_service `PricingService`, proto_sha256, rpcs `[PriceCart]`,
estimated_loc), `startup` (`["node", "<entry>.js"]`, `PORT`, `tcp`), and `tasks[0]` embedding
`pricing.proto` + the stringent spec text (strategy semantics, rounding, tax ordering, cap,
promo-min, error taxonomy). *Serves FR-1, FR-8, FR-10, FR-12.*

**S6 — FR-47 rename pass** Apply the rename map (OQ-5) to the proto + spec text so Liferay tells are
neutralized; ship the renamed contract. *Serves FR-11 (reframed).*

**S7 — Validate** Re-run the existing behavioral tests (OB cells must be byte-identical/unaffected
by S3), then a local dry-run of the pricing cell against a hand-written reference Node server to
confirm G1–G7 pass. *Serves FR-9, FR-13.*

## Risks
- S3 touches a shared hot path (`prepare_node_workdir`). Mitigation: default-to-`demo.proto` keeps
  OB cells unchanged; add a regression test asserting OB provisioning is identical.
- S2 stub generation is a committed artifact — must pin the `grpc_tools` / protobuf runtime version
  to match `demo_pb2.py`'s generator to avoid wire/runtime skew.
