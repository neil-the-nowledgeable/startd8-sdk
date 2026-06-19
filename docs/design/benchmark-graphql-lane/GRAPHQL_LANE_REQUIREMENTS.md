# Track 2 GraphQL Protocol Support — Requirements

**Version:** 0.3 (Cross-reference research + hybrid GraphQL design)
**Date:** 2026-06-18
**Status:** Draft (planning-corrected; pre-implementation)
**Plan:** `GRAPHQL_LANE_PLAN.md`
**Scope:** Add GraphQL as the third benchmark protocol (after gRPC and the merged REST/HTTP lane),
landing on the FR-10 protocol-pluggable seam, with a GraphQL pricing seed.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass **falsified two requirements outright** and narrowed two more. The headline: the
> REST lane already built the HTTP foundation, so GraphQL is **one suite file + one seed, zero harness
> change** — *even lighter than REST*. The value is in catching what GraphQL adds (the 200-on-error
> convention) and what it does NOT need (protocol-field routing, a protocol-adapter abstraction).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1: add a GraphQL lane like REST | GraphQL reuses ALL the REST HTTP machinery (readiness http mode, httpx, SuiteResult, sandbox, grpc-aware provisioning) — zero harness change | FR-1 narrowed to "one suite + one seed" |
| FR-2: route via the seed `protocol` field | The `protocol` field is **not load-bearing** (nothing reads it); dispatch is `_SUITES.get(service)` + `readiness_mode` | **FR-2 falsified** → route the same way REST does (readiness http + suite-by-name); protocol field stays metadata |
| FR-3: GraphQL-aware readiness | The REST lane's http-liveness `wait_ready` already suffices | FR-3 narrowed to "reuse"; graphql probe optional |
| FR-4: assert the response | GraphQL returns **HTTP 200 even on errors** (errors in the body) — the one genuinely GraphQL-specific convention | FR-4 sharpened (the real work) |
| FR-5: provision a GraphQL library | Needs `graphql-core` via the existing `requirements.txt` path; REST's zero-dep quick win does NOT carry — but the **oracle can be stdlib** | FR-5 corrected |
| FR-9: extract a protocol adapter | The **suite file already IS the protocol adapter**; only readiness + provisioning are shared and already exist | **FR-9 falsified** → re-scoped to a non-requirement (avoid over-engineering) |

**Resolved open questions:**
- **OQ-1 → Not load-bearing.** Dispatch is readiness mode + service-name suite registry; `protocol` is metadata.
- **OQ-2 → Errors in the body at HTTP 200.** The suite asserts `data` present / `errors` absent (success) or `errors` present (failure) — never on HTTP status.
- **OQ-3 → Needs a library for a realistic server** (graphql-core, pure-python → `--only-binary` works), via `requirements.txt`; the validation oracle is stdlib (fixed query).
- **OQ-4 → http-liveness suffices.** No GraphQL-specific readiness mode required.
- **OQ-5 → Don't extract an adapter.** The suite is the adapter; a registry is YAGNI.

---

## 1. Problem Statement

The Track 2 harness scores model-generated services over loopback. It now supports gRPC and REST/HTTP
behavioral lanes. GraphQL is a major modern API protocol (and a Liferay headless surface), so the
benchmark should be able to host GraphQL seeds. GraphQL is HTTP-based, so it should reuse the REST
lane's HTTP machinery — but it has its own request/response shape (a single `POST /graphql` endpoint,
SDL schema, and an `errors` array in the body).

| Component | Current State | Gap |
|-----------|--------------|-----|
| Service launch + sandbox | protocol-agnostic | none expected |
| Readiness | tcp + http modes (REST lane) | maybe a GraphQL-aware probe |
| Suite client | gRPC + REST (httpx) | needs a GraphQL client convention |
| Provisioning | grpc-aware; stdlib REST = zero-dep | GraphQL likely needs a library |
| Seed routing | `protocol` field on seeds | route GraphQL seeds via it |

## 2. Requirements

**FR-1 — GraphQL via the existing HTTP foundation (no harness change).** Host a model-generated GraphQL
server and score it by **reusing** the REST lane's machinery — `readiness.py` http mode, the httpx suite
client, `SuiteResult`/`_SUITES`, `run_service_sandboxed`, grpc-aware provisioning. *Planning-corrected:*
this is **one suite file + one seed**, no harness change.

**FR-2 — Route the same way REST does (not via a protocol field).** A GraphQL seed routes through the
HTTP path via `startup.readiness:"http"` + a graphql suite registered under its service name. *Planning-
corrected:* the seed `protocol` field is **descriptive metadata, not load-bearing** — nothing in the
harness dispatches on it; do not build protocol-field routing.

**FR-3 — Readiness: reuse http-liveness.** GraphQL readiness uses the REST lane's `wait_ready(mode="http")`
(a server answering any HTTP response = up). A GraphQL `{__typename}` probe is an optional nicety, not
required.

**FR-4 — Two-layer GraphQL ground-truth suite.** The suite POSTs `{"query","variables"}` to `/graphql`
and asserts the **errors-in-body convention** (success = `data` present + no top-level `errors`; failure
= `errors` present — **always HTTP 200**, never on HTTP status). Two layers: **(L1) cross-protocol core**
— the G1–G7 pricing assertions over a *fixed* selection set that mirrors the REST/gRPC response, so the
core stays comparable across protocols; **(L2) GraphQL-hardening probes** — selection-driven computation,
the derivation field, and partial-error paths (FR-10). Returns the same `SuiteResult`, registered in
`_SUITES`; a reusable `data`/`errors` helper encodes the convention.

**FR-5 — Provisioning + oracle use `graphql-core`.** A realistic GraphQL server needs `graphql-core`
(pure-python → `pip --only-binary` works) via the existing `requirements.txt` provisioning path.
*Corrected from v0.2:* the validation **oracle also uses `graphql-core`** — the hybrid's selection-driven
resolution + partial-error paths (FR-10) need a real GraphQL engine, not a stdlib query-matcher. The
oracle test is **gated** via `pytest.importorskip("graphql")` (the repo's gated-test pattern), and
`graphql-core` is added to the dev extra. REST's zero-dep quick win does not carry.

**FR-6 — Hybrid GraphQL pricing seed (basket operation + computed-field graph).** The schema combines the
two candidate shapes: a single **`basket(input: BasketInput!): PricedBasket!`** operation (the pure-
calculator carve — all pricing inputs explicit, deterministic, resolution upstream) whose return type is
a **graph of computed fields** the model must *resolve*, not echo (real GraphQL idiom):
`PricedBasket{ lines:[PricedLine!]!, subtotalNetPayable, subtotalNetPayableWithTax }`,
`PricedLine{ sku, netPayable, netPayableWithTax, taxValue, priceOnApplication, adjustment:AdjustmentBreakdown! }`,
`AdjustmentBreakdown{ amount, effectivePercent, tierPercents:[String!]! }`. Same G1–G7 semantics.
Types/fields are **FR-47-renamed** to neutral names. The spec requires **HTTP 200 + `errors`** for invalid
input. Money is **decimal strings** (a documented, deliberate divergence from Liferay's `Double`, which
fails the rounding cases). Field *semantics* are authored from the canonical **tagged** Liferay DTO
(delivery-order `Price.java`, a `7.4-ga` release), NOT the `master` OpenAPI (flagged as resembling our
own seed — a provenance risk; see §5).

**FR-7 — Scoring parity (no change).** GraphQL coverage folds into the composite identically (`scoring.py`
is protocol-blind).

**FR-8 — Backward compatibility.** gRPC and REST seeds/cells are byte-identical; GraphQL is additive
(regression-guarded).

**FR-9 — No protocol-adapter abstraction (non-requirement).** *Planning-corrected:* the **suite file is
already the protocol adapter** (it encapsulates the per-protocol call + error convention); only readiness
mode and provisioning are shared, and both already exist. Extracting a protocol-adapter registry is YAGNI
and is explicitly out of scope — documenting the pattern is enough.

**FR-10 — Memorization resistance via GraphQL selection sets.** Exploit GraphQL's *client-chosen*
selection sets as the anti-memorization mechanism — the one thing gRPC/REST cannot do (their response
shape is fixed, so a memorized "return the whole object" impl passes). The seed + suite must implement:
- **(a) Selection-driven computation** — the suite probes the **(G-case × selection-set)** matrix; a
  memorized compute-everything implementation over-computes, mis-orders, or breaks on a specific nested
  selection.
- **(b) Derivation field** — `AdjustmentBreakdown.tierPercents` exposes the per-tier resolved percentages
  **as queryable data**; no real API or tutorial does this, so it can't be recalled — and it tests the
  arithmetic harder.
- **(c) Partial-error paths** — a basket with one invalid line returns HTTP 200 with partial `data` (valid
  lines resolved) + `errors[].path` pinpointing the bad line; correct per-field error propagation can't be
  faked from a memorized happy path.
- **(d) FR-47 perturbation** — neutral renamed types/fields defeat token-level matching against Liferay or
  pricing tutorials.

Claim: **memorization-resistant by construction**, not "impossible" — a model would need this exact renamed
schema + selection matrix + derivation semantics (vanishingly unlikely for a synthetic seed), and selection
sets force per-field resolution even on a near-miss. This is what earns GraphQL its place in the benchmark
as more than "REST with one endpoint."

### 2.1 Quick Wins / Low-Hanging Fruit (surfaced by planning)

- **QW-1 — Even lighter than REST.** GraphQL inherits the entire HTTP foundation REST built → one suite
  file + one seed, zero harness change. The 3rd protocol is the cheapest yet — the REST lane's
  protocol-pluggable thesis realized. (The hybrid + FR-10 hardening below add deliberate cost on top.)
- **QW-2 — Reusable error helper.** An `errors-in-body` assertion helper serves every future GraphQL seed.
- **QW-3 — Readiness already works.** The http-liveness mode needs no GraphQL-specific addition.
- **QW-4 — Selection sets ARE the anti-memorization lever (FR-10).** GraphQL's client-chosen response
  shape — unique vs gRPC/REST's fixed shape — is exploited so a memorized solution can't be pasted; the
  protocol's own idiom does double duty as a contamination control. (Cost: the oracle now needs a real
  GraphQL engine, gated `graphql-core` — the v0.2 "zero-dep oracle" no longer holds.)
- **QW-5 — Avoided over-engineering.** Planning showed the protocol-adapter registry (FR-9) is unnecessary
  — the suite-as-adapter pattern is the correct minimal abstraction. A non-build is a win.

## 3. Non-Requirements

- **Not** GraphQL subscriptions / WebSockets — query/mutation over HTTP only.
- **Not** federation / gateway / stitching.
- **Not** introspection-based schema validation — the suite tests behavior via known queries.
- **Not** replacing the gRPC or REST lanes.

## 4. Open Questions

All five v0.1 open questions were resolved by planning (see §0). Remaining items are
implementation-time calibrations:

- **CQ-1** GraphQL spec fidelity — the SDL + errors-in-body rule in `requirements_text` must pin the OPEN
  choices (partial-results handling, error `extensions.code` vs message) precisely enough for deterministic
  ground truth.
- **CQ-2** Whether the seed spec recommends a specific minimal library (`graphql-core`) or leaves the
  server impl open; pin the allowed deps either way.

## 5. Cross-reference & provenance

Liferay headless **generates REST + GraphQL from one `rest-openapi.yaml`** (`generateGraphQL` default true);
the GraphQL `Price` type is field-identical to the REST DTO — so our gRPC + REST + GraphQL seeds mirror
Liferay's own one-contract / N-protocols architecture. Reference assets: GraphQL endpoint `/o/graphql`;
**live SDL via GraphiQL introspection at `/o/api`** (no static SDL file exists);
`headless-commerce-delivery-catalog-impl/rest-openapi.yaml`; canonical pricing DTO = delivery-order
`Price.java` (7.4-ga javadoc, with `discountPercentageLevel1..4`).

**Deliberate, documented divergences from Liferay** (the seed's ground truth must state these):
- Liferay has **no basket-pricing operation** in any protocol — pricing is a computed `Price` field on a
  SKU/product. We keep a `basket(...)` operation for the pure-calculator carve + cross-protocol parity.
- Liferay money is `Double`; we use **decimal strings** (Double fails the rounding cases the suite tests).

**Provenance guardrail (bias-audit discipline):** the `master` delivery-catalog OpenAPI carries an enriched
`Price` that *resembles our own derived seed* — possibly evolved-upstream or a fork. Author field
**semantics** from a **tagged release** (`7.4-ga###` delivery-order `Price.java`), not `master`, to avoid a
circular cross-reference.

---

*v0.2 — Post-planning self-reflective update. The planning pass **falsified 2 requirements** (FR-2
protocol-field routing — the field isn't load-bearing; FR-9 protocol-adapter abstraction — the suite is
already the adapter), **narrowed 3** (FR-1/FR-3/FR-5 → reuse the REST foundation), **sharpened 1** (FR-4
— the HTTP-200-on-error convention is the one real GraphQL-specific concern), **5 quick wins** (§2.1), all
5 open questions resolved. The loop earned its keep: GraphQL is the 3rd protocol and the cheapest yet —
one suite + one seed, zero harness change — concretely realizing the FR-10 protocol-pluggable thesis while
catching the two over-builds a naive draft would have shipped.*

*v0.3 — Cross-reference research + hybrid design. Liferay generates REST+GraphQL from one OpenAPI (our trio
mirrors that); pricing is a `Price` *field* (no basket op), money is `Double`. Adopted a **hybrid**: a
`basket(input)` operation (pure-calculator carve) returning a **computed-field graph** (GraphQL idiom), with
GraphQL **selection sets exploited as the memorization-resistance mechanism** (new FR-10: selection-driven
probing + a `tierPercents` derivation field + partial-error paths + FR-47 renaming). FR-4 → two-layer suite;
FR-5/oracle now use gated `graphql-core` (the v0.2 stdlib oracle no longer holds). Divergences from Liferay
(basket op, decimal-strings) deliberate + documented; field semantics sourced from the tagged DTO (§5).*
