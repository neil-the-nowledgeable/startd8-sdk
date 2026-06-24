# Round 3 — Generated-Frontend Seed + Lane Scoping (the 10th, BONUS service)

**Version:** 0.1 (scoping only — NO implementation)
**Date:** 2026-06-24
**Status:** Design/scoping. The deliverable is the cost ledger + reuse-vs-net-new + risks for adding the
**contestant-generated frontend** as a 10th seed — a **BONUS** service whose failure is contained by
canonical substitution (it can never zero a model). No code in this pass.
**Owner SDK area:** `startd8.benchmark_matrix.behavioral` (Go lane + startup-contract reuse) + the
Round-3 fleet orchestrator + the frontend gate + Adapter-A HTTP driver.
**Parents:**
- `docs/design/round3-full-app/JOURNEY_DESIGN.md` (v0.2 — transport-agnostic journey + bonus model)
- `docs/design/round3-full-app/FRONTEND_OPENAPI_CONTRACT.md` (the contract + gate this seed targets)
- `docs/design/round3-full-app/CONTAINERIZATION_SCOPING.md` (the **Go container lane** this reuses)
**Canonical reference:** `~/Documents/dev/micro-service-demo/microservices-demo-latest/src/frontend/`
(`main.go`, `handlers.go`, `rpc.go`, `Dockerfile`) + `release/kubernetes-manifests.yaml` (env wiring).

---

## 1. The seed at a glance

| Property | Value |
|---|---|
| Service | `frontend` (10th service; **BONUS**, not required) |
| Language | **Go** — reuse the existing Go container lane + `setup_go_stubs` (no new lane) |
| Target file (seed) | `src/frontend/*.go` (multi-file: `main.go` router + `handlers.go` + `rpc.go`, or a model's single-file equivalent) |
| Surface | **HTTP/HTML + form endpoints** (gorilla/mux upstream; any Go HTTP router acceptable) |
| Listens on | `:8080` (containerPort 8080; canonical Service port 80) |
| Probe | HTTP `GET /_healthz` → `ok` (or `GET /`) |
| Backend deps dialed | **7** journey gRPC deps (§2) |
| Scoring | **BONUS** — additive, never subtractive (§4) |
| Failure mode | gate FAIL → **substitute canonical frontend**; backend scoring unaffected |

The frontend is a **meatier artifact** than the leaf backend services: it's not one RPC handler but a
multi-route HTTP app that **orchestrates 7 backends** (the §2 fan-out) and renders HTML/redirects. That
is exactly why it's scored as a bonus with a substitution net rather than as a gating leaf.

---

## 2. Dependencies — `dependency_addr_env` (the 7 journey deps)

From `main.go` `mustMapEnv` + `release/kubernetes-manifests.yaml` frontend env block. The generated
frontend's startup contract declares these 7 `*_SERVICE_ADDR` envs (the harness binds them to the
contestant fleet, exactly as the backend seeds' `dependency_addr_env` are bound today):

| `*_SERVICE_ADDR` env | Backend service | gRPC port (canonical) |
|---|---|---|
| `PRODUCT_CATALOG_SERVICE_ADDR` | productcatalogservice | 3550 |
| `CART_SERVICE_ADDR` | cartservice | 7070 |
| `CURRENCY_SERVICE_ADDR` | currencyservice | 7000 |
| `SHIPPING_SERVICE_ADDR` | shippingservice | 50051 |
| `CHECKOUT_SERVICE_ADDR` | checkoutservice | 5050 |
| `RECOMMENDATION_SERVICE_ADDR` | recommendationservice | 8080 |
| `AD_SERVICE_ADDR` | adservice | 9555 |

Notes:
- The frontend does **NOT** dial payment/email directly — those are reached transitively via
  `Checkout.PlaceOrder` (the 6-dep checkout orchestration owned by checkoutservice). So the frontend's
  own dep set is 7, not 9.
- `SHOPPING_ASSISTANT_SERVICE_ADDR` (8th canonical env) is **non-journey** (`/assistant`, `/bot`) and is
  **out of scope** for the seed — neither required nor gated. A generated frontend may omit it entirely.
- **adservice is the only Java service** and is the v2-defer candidate in `CONTAINERIZATION_SCOPING.md`
  (OQ-C5). If the round runs **without** adservice, the frontend's `AD_SERVICE_ADDR` dep must degrade
  gracefully (ads are non-critical — the canonical handler log-and-continues on ad failure, §3 of the
  contract). So the frontend seed must tolerate a **missing ad backend** without failing the journey —
  this is both a faithfulness point and what lets the frontend ship in a Java-deferred v1.

---

## 3. The startup / serve contract

Same shape as the backend behavioral startup contracts (`behavioral/contract.py` `StartupContract` +
`resolve_serve_command`), with HTTP specifics:

- **Build/serve command** — reuse the **Go lane**: `setup_go_stubs` injects the `hipstershop` local
  stub module + `replace` (the frontend imports the same `genproto` gRPC clients the backends generate
  from), then `go build -o server` → run `./server`. No new launcher logic — the Go `_default` launcher
  + container CMD pattern in `CONTAINERIZATION_SCOPING.md` §2 (Go row) applies unchanged.
- **Port** — `PORT=8080` (or harness-assigned); the gate/Adapter-A driver discovers it from the contract.
- **Readiness** — HTTP `GET /_healthz` → 200 `ok`, or `GET /` → 200, within the startup deadline. This
  is a **NET-NEW startup-contract variant**: existing contracts are gRPC-readiness (a gRPC health/first-
  call probe); the frontend needs an **HTTP-readiness** probe. Small addition to `StartupContract`
  (an `http_health` mode alongside the gRPC mode).
- **Dep binding** — the harness binds the §2 envs to the live contestant fleet before boot, identical to
  backend dep binding.

---

## 4. Scoring — BONUS (additive, never subtractive)

Per `JOURNEY_DESIGN.md` §4.2. The frontend contributes only **upside**:

- **(a) Frontend service score** — scored only if the gate passes; rewards route correctness + the §2
  orchestration fidelity (did each route fan out to the expected backends per the contract's §3 map) +
  clean redirects/pages. Absent/failed frontend → **0 bonus** (never negative).
- **(b) `journey_via_generated_frontend` flag** — binary credit: the real locust mix completed
  end-to-end **through the contestant's own frontend** (gate passed AND Adapter A green on it).
- **Folding rule** — report `backend_score` (the ranked axis) and `frontend_bonus` as **separate
  columns**; rank on backend, use the bonus as a tie-break / labeled "+frontend" credit so a great
  frontend never lets a weak-backend model outrank a strong-backend one (OQ-J3 caps the magnitude).
- **On substitution** — Adapter A still runs over the canonical frontend and yields a
  `canonical_journey_completed` fleet-authenticity flag, but **that is not frontend bonus** (earned by
  the reference impl, not the contestant). Frontend bonus stays 0.

The point: **a model is never zeroed for a bad frontend.** Backend layered scoring (`JOURNEY_DESIGN.md`
§4.1) runs over the contestant backends regardless of which frontend is mounted.

---

## 5. Reuse vs net-new (the ledger)

**REUSE (already exists — relocate/parameterize):**
- **Go container lane** — base image, `setup_go_stubs` stub vendoring + `replace`, `go build`, the
  distroless runtime, and the parameterized Go Dockerfile template (`CONTAINERIZATION_SCOPING.md` §2/§7b
  Go row). The frontend is "just another Go service" to the build layer.
- **The canonical upstream `src/frontend`** — used **as the substitution fallback image** (the
  model-invariant reference impl), wired via the §2 envs. Build once, reuse every round.
- **The journey driver's HTTP adapter (Adapter A)** — the same form-encoded HTTP driver runs over either
  frontend (the contract is the seam); written once for Adapter A, not per-frontend.
- **Dep-binding machinery** — the `*_SERVICE_ADDR` env wiring + the egress-denied internal network are
  the same the backend fleet already uses.
- **Startup-contract framework** — `StartupContract` + `resolve_serve_command` extended with an
  HTTP-readiness mode (small).

**NET-NEW:**
- **The frontend seed itself** — its seed entry (`seeds-index.json`), prompt/spec, target file(s), and
  the **HTTP-readiness startup contract** variant.
- **The journey-facing HTTP contract suite** (`FRONTEND_OPENAPI_CONTRACT.md` §1–§3) as an executable
  spec the gate runs.
- **The substitution mechanism** — the gate verdict → mount-generated-or-canonical switch, the
  `frontend=generated|canonical-substituted` run-report field, and clean fail-to-canonical (no
  partial-mount).
- **The 7-way orchestration validation** — observing (via known-good-fleet call counters) that the
  generated frontend's routes fan out to the expected backends (§2 map), feeding the bonus service score.
- **The frontend bonus scorer + folding** into the scorecard (separate column, tie-break, cap).

---

## 6. Effort read + risks

**Effort: moderate — heavier than a leaf backend suite, lighter than the whole container layer.** The
build/run mechanics are **near-free reuse** (Go lane + stubs + Dockerfile template already exist; the
frontend is a Go service). The genuine new cost is concentrated in **(a) the gate** and **(b) the
substitution + bonus scoring** — neither is large, but the gate must be *robust*. Call it ≈ **one
behavioral suite's worth**, most of it the contract suite + gate + substitution wiring, since the lane
and fallback image are reuse.

**Risks:**
- **R1 — meatier artifact, lower pass rate.** The frontend orchestrates 7 backends across 6 routes with
  session state — a much bigger ask than a single-RPC leaf. Expect many models to fail the gate and fall
  to canonical. That's **by design** (bonus, not gate), but it means the generated-frontend path is the
  *rarer* signal; report it as a discriminating bonus, not a baseline expectation.
- **R2 — gate robustness (the load-bearing risk, = OQ-J1).** A *subtly-broken* generated frontend (boots,
  serves routes, but mis-orchestrates — e.g., checkout renders a confirmation page **without a real
  order id**, or add-to-cart silently drops items) must **fail the gate and fall to canonical**, NOT pass
  and produce misleading Adapter-A journey results. The decisive defense is the gate's **stateful
  end-to-end checkout against known-good backends** (contract §4 stage 3): it catches "looks right but is
  wrong." If the gate is too loose, a broken frontend pollutes the journey signal; if too strict,
  near-passing frontends lose deserved bonus. **Lean strict** — fail to canonical cleanly.
- **R3 — fail-to-canonical must be clean.** No partial mount, no half-substituted fleet, no silent
  fallback. Every run must record **which frontend ran** + the gate verdict + reason (OQ-J4), so a
  substituted run is never mistaken for a generated-frontend pass.
- **R4 — adservice-deferred coupling.** If the round runs without the Java adservice (OQ-C5), the
  frontend's `AD_SERVICE_ADDR` dep must degrade gracefully (ads are non-critical). A generated frontend
  that hard-fails on a missing ad backend would fail the gate spuriously — but per the contract, ads
  aren't on the journey success path, so the gate's checkout completion test should not require ads.
  Encode "ad/rec failures are non-critical" in the gate.
- **R5 — double-attribution (= OQ-J2).** When the generated frontend AND contestant backends both run, an
  Adapter-A failure could be the frontend's or a backend's fault. The always-on direct-gRPC Adapter B
  (contestant-backends-only) is the disambiguator: B-passed-but-A-failed-on-generated-frontend →
  attribute to the frontend (bonus loss), not the backend.

---

## 7. Open questions (frontend lane)

- **OQ-F1 — single-file vs multi-file frontend seed.** Canonical splits router/handlers/rpc across files.
  Should the seed demand multi-file (more faithful, harder) or accept a single-file Go frontend? Lean
  permissive (single-file acceptable) since the gate is behavioral — the contract cares about routes +
  fan-out, not file layout.
- **OQ-F2 — HTML-template fidelity vs functional fidelity.** The gate is behavioral (journey completes),
  so a generated frontend need not match the canonical HTML templates — only the routes, form fields,
  fan-out, and response *kinds*. Confirm the bonus scorer rewards *functional* orchestration, not
  template cosmetics.
- **OQ-F3 — does the frontend bonus tempt models to over-invest?** Since it's pure upside, a model could
  spend disproportionate effort on the frontend at the expense of backends. The folding cap (OQ-J3) and
  backend-first ranking (§4) should neutralize this — confirm the cap is low enough.
