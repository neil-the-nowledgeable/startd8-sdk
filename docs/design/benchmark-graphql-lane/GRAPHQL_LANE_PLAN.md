# Track 2 GraphQL Protocol Support — Implementation Plan

**Version:** 1.2 (tracks requirements v0.3 — hybrid)
**Date:** 2026-06-18
**Tracks:** `GRAPHQL_LANE_REQUIREMENTS.md` (drove this plan; updated to v0.2 by it; v0.3 added the hybrid
schema + memorization-resistance after cross-reference research). Planning falsified FR-2 (protocol-field
routing — not load-bearing) and FR-9 (protocol-adapter abstraction — the suite is the adapter); both
re-scoped. The build now implements the **hybrid** (FR-6): a `basket(input)` operation returning a
computed-field graph, a **two-layer suite** (cross-protocol core + FR-10 hardening probes: selection-driven
+ `tierPercents` derivation + partial-error paths + FR-47 rename), and a **gated `graphql-core` oracle**.

Maps each requirement onto the merged harness (`src/startd8/benchmark_matrix/`, incl. the just-shipped
REST lane). Headline: GraphQL is **even lighter than REST** — the REST lane already built the HTTP
foundation, so GraphQL is **one suite file + one seed, zero harness change** — and the planning also
falsifies two v0.1 requirements (protocol-field routing, and extracting a protocol adapter).

---

## Discoveries (feed the reflection pass)

| What the v0.1 requirements assumed | What planning revealed (file:line) |
|---|---|
| **FR-1** "add a GraphQL lane (like the REST lane)" | The REST lane already added the HTTP foundation. GraphQL reuses ALL of it: `readiness.py` http mode, the httpx suite client, `SuiteResult`/`_SUITES`, `run_service_sandboxed`, grpc-aware provisioning. **Zero harness change** — even lighter than REST (which had to build the foundation). |
| **FR-2** route GraphQL via the seed `protocol` field | The `protocol` field is **NOT load-bearing** — grep finds nothing in `benchmark_matrix/` reading it (it's pure metadata on the REST seed). Dispatch is `_SUITES.get(service)` (`execute.py:130`) + `StartupContract.readiness` (`execute.py:149-150`). GraphQL routes the SAME way REST does: `readiness:"http"` + a graphql suite registered by service name. **No protocol-field routing exists or is needed.** |
| **FR-3** a GraphQL-aware readiness probe | The REST lane's http-liveness `wait_ready(mode="http")` already suffices (a server answering ANY HTTP response = up). A graphql `{__typename}` probe is an optional nicety, not a requirement. |
| **FR-4** assert the GraphQL response | **The genuinely GraphQL-specific thing:** GraphQL returns **HTTP 200 even on errors** — validation errors live in the body's `errors` array, not the HTTP status. The suite asserts on `data`/`errors`, fundamentally unlike REST's "400 = invalid". This convention lives **inside the suite file**. |
| **FR-5** provision a GraphQL library | A realistic GraphQL server needs `graphql-core` (pure-python → `pip --only-binary` works) via the EXISTING `requirements.txt` provisioning path (`provision.py`). REST's zero-dep stdlib quick win does **not** carry. BUT the validation **oracle can be stdlib** (it answers a FIXED query, so it can pattern-match without a GraphQL engine). |
| **FR-9** extract a protocol-adapter abstraction | **Don't.** The suite file ALREADY encapsulates the per-protocol call/error convention (gRPC stub vs REST-400 vs GraphQL-errors-array). Only readiness mode + provisioning are shared, and both already exist. A protocol-adapter registry is YAGNI — the right abstraction ("suite = adapter") is already in place. |
| **FR-7** scoring needs GraphQL awareness | `scoring.py` consumes a float coverage — protocol-blind. **Zero change.** |

## Step-by-step

**S1 — GraphQL suite** (`behavioral/graphql_pricing_suite.py`), parallel to `rest_pricing_suite.py`:
an httpx client that POSTs `{"query": ..., "variables": {...}}` to `/graphql`, and asserts the GraphQL
convention — success = `data.priceBasket` present and no top-level `errors`; invalid = `errors` present
(HTTP 200 throughout). Same G1–G7 + rollup pricing ground truth. Register in `_SUITES`. A small
`_gql_ok`/`_gql_error` helper encodes the errors-in-body convention (reusable for future GraphQL seeds).
*Serves FR-1, FR-3 (reuse), FR-4, FR-6, FR-7.*

**S2 — GraphQL pricing seed** (`scripts/gen_graphql_pricing_seed.py` + `seed-graphql-pricingservice.json`):
`startup.readiness:"http"` + `health_path`; the SDL schema + `priceBasket(input: BasketInput!):
PricedBasket` query embedded in `requirements_text`, with the **errors-in-body** rule spelled out
(validation → `errors` array at HTTP 200, NOT a 4xx); register in `hardened-index` (protocol "graphql",
metadata only). Allow `graphql-core` in deps; the model may also hand-roll. *Serves FR-2 (via readiness,
not protocol-field), FR-5, FR-6.*

**S3 — Validation** (`tests/.../test_graphql_pricing_suite.py`): a stdlib (zero-dep) reference GraphQL
server that pattern-matches the fixed `priceBasket` query, runs the decimal algorithm, and returns
`{"data": {...}}` or `{"errors": [...]}` at HTTP 200 — proving the suite reaches 15/15 and the http
readiness sees it ready. A gRPC+REST regression asserts existing lanes are byte-identical.
*Serves FR-4, FR-6, FR-7, FR-8.*

**S4 — Docs note**: the `protocol` field stays descriptive metadata; the real seam is (readiness mode,
suite-by-service-name), and the suite file is the protocol adapter. No abstraction extracted (FR-9 →
non-requirement). *Serves FR-9 (re-scoped).*

## Risks
- The model could return a 4xx on GraphQL errors (a common mistake) — the seed spec must explicitly
  require HTTP 200 + `errors`; the suite must assert exactly that.
- Partial results (GraphQL can return both `data` and `errors`) — the pilot's single-field pricing keeps
  it simple: success = `data` present and no `errors`; failure = `errors` present. Documented.
- `graphql-core` provisioning offline — it's pure-python so `pip --only-binary=:all:` works; confirm in
  the seed's allowed deps. The reference oracle avoids it entirely (stdlib).
