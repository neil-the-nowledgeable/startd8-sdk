# Track 2 REST/HTTP Behavioral Lane — Implementation Plan

**Version:** 1.1 (tracks requirements v0.2)
**Date:** 2026-06-18
**Tracks:** `REST_LANE_REQUIREMENTS.md` (drove this plan; updated to v0.2 by it). S1 = FR-11 (shared
readiness primitive); the readiness *mode* + provisioning + suite-client are all keyed off the seed so
the dispatch is protocol-pluggable (FR-10), not REST-hardcoded.

Maps each requirement to the real Track 2 harness (`src/startd8/benchmark_matrix/`). The headline:
contact with the code **falsifies the "REST = heavy harness work" premise** — most of the harness is
already protocol-agnostic, and an HTTP readiness probe already ships in the deploy harness.

---

## Discoveries (feed the reflection pass)

| What the v0.1 requirements assumed | What planning revealed (file:line) |
|---|---|
| **FR-1** extend the harness to host HTTP servers | `run_service_sandboxed` (`sandbox.py:276`) is **100% protocol-agnostic**: it launches argv on a port, waits readiness via a **raw TCP connect** (`_port_ready`, `sandbox.py:205` — `socket.create_connection`), runs a caller-supplied `client(port)` pass-through, and tears down. It neither knows nor cares about gRPC vs HTTP. **Zero changes.** |
| **FR-2** build an HTTP readiness probe | The **shipped deploy harness** already has a battle-tested, stdlib-only probe: `_probe(url)->"ok"\|"http"\|"down"` with a probe-order `/health → /openapi.json → /` and `_wait_until_ready` (`deploy_harness/server.py:40-83,185-229`). **Lift it, don't build.** |
| **FR-3** build an HTTP suite-client framework | `httpx` is **already a core dependency** (`pyproject.toml:31`); `_SUITES` is `Dict[str, Callable[[int], object]]` and `SuiteResult`/`.coverage`/`.to_dict()` are **fully protocol-neutral** (`charge_suite.py:38-53`). A REST suite is **just a new file** populating the same dataclass with httpx. No framework. |
| **FR-4** REST dependency provisioning | REST **skips proto provisioning entirely** (`_PROTO_BY_SERVICE`/`prepare_node_workdir` are gRPC-only, `execute.py:38-89`). A minimal **stdlib** REST server (Python `http.server`, Node `http`) needs **zero vendored deps**. The only real fix: `provision.py:_COMMON["python"]=["grpcio","protobuf"]` (`provision.py:42`) is installed unconditionally — make it protocol-aware so REST doesn't pull grpc. |
| **FR-5** the seed schema needs new REST fields | `StartupContract` (`contract.py:20-46`) **already has a `readiness` field** (default `"tcp"`). The whole schema change is: wire it + add an additive `health_path`. Backward-compatible (defaults preserve gRPC). |
| (latent) `readiness:"tcp"` is actually honored | It is **not** — `readiness` is read from the seed (`from_seed`) but **never consumed**; the harness always TCP-probes. Wiring readiness closes a real latent contract gap (correctness + quick win). |
| (implicit) this is a one-off "REST hack" | Because the harness is protocol-agnostic, the same ~150-line change is a **protocol-dispatch generalization** — GraphQL / any HTTP-shaped protocol slots in later for ~free. |
| **FR-7** scoring needs REST awareness | `scoring.py` fold (`FUNCTIONAL_WEIGHT`, line 40) consumes a float coverage — **protocol-blind. Zero changes.** |

## Step-by-step

**S1 — Shared readiness primitive** (`benchmark_matrix/readiness.py`, ~25 lines). Extract the deploy
harness's `_probe(url)` into a shared stdlib module exposing `wait_ready(port, mode, *, health_path,
timeout)` where `mode ∈ {"tcp","http"}`; `http` polls `/health`(or `health_path`)→2xx with a TCP-connected
fallback, degrades honestly on timeout. The deploy harness and the behavioral lane both import it (one
source of truth). *Resolves OQ-2; serves FR-2.*

**S2 — Wire readiness into the behavioral cell** (`execute.py` + `sandbox.py`). Pass the seed's
`StartupContract.readiness` (+ `health_path`) through `run_behavioral_cell` → `run_service_sandboxed`'s
readiness wait, defaulting to `"tcp"` (gRPC unchanged). Closes the latent gap that `readiness` was
declared-but-ignored. *Serves FR-1 (the only real "host HTTP" need is the readiness mode), FR-5, FR-8.*

**S3 — Protocol-aware provisioning** (`execute.py` + `provision.py`). Route REST seeds around proto
provisioning, and make `_COMMON` deps protocol-aware so a REST Python cell installs `httpx` (or nothing
for stdlib) instead of `grpcio/protobuf`. A minimal stdlib REST server needs no vendored runtime.
*Serves FR-4 (much reduced).*

**S4 — A REST suite** (`behavioral/rest_pricing_suite.py`), parallel to `pricing_suite.py`: httpx client,
hit the pricing endpoint(s) with JSON bodies, assert status + response JSON (the same G1–G7 ground truth),
return a `SuiteResult`. Register in `_SUITES`. *Serves FR-3, FR-6, FR-7.*

**S5 — REST seed + contract** (`docs/design/model-benchmark/seeds/seed-rest-pricingservice.json` +
`scripts/gen_rest_pricing_seed.py`): `startup.readiness:"http"`, `health_path`, REST endpoint contract
(OpenAPI-derived) embedded in `requirements_text`; register in `hardened-index.json`. *Serves FR-5, FR-6.*

**S6 — Validation** (`tests/.../test_rest_pricing_suite.py`): a correct reference REST server (stdlib,
~zero deps) proves the suite reaches 1.0 (the Node-oracle pattern from Phase 1); a gRPC regression test
asserts existing cells are byte-identical. *Serves FR-7, FR-8.*

**S7 — Multi-service groundwork** (doc-only here): note how a seed could declare >1 service + an
integration suite (the harness already hosts one process; a second port + a second readiness is the
delta). *Serves FR-9.*

## Risks
- REST contracts are looser than proto (status codes, JSON shapes, error envelopes are OPEN) → the REST
  suite must pin them explicitly; the contract embedding (OpenAPI vs prose) needs a decision (OQ-3).
- Sharing `readiness.py` with the deploy harness must not regress the deploy harness's probe order/timing
  — extract carefully + keep its tests green.
- A "realistic" REST server (FastAPI) needs deps; the pilot pins a minimal/stdlib server to stay zero-dep.
