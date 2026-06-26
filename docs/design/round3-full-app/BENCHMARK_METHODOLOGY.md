# Round 3 — System Benchmark Methodology (as shipped)

**Version:** 1.0 · **Date:** 2026-06-25 · **Status:** SHIPPED + live-validated on `origin/main`.

> This is the **methodology reference for the built system** — what the Round-3 benchmark measures and
> how, grounded in the code under `src/startd8/benchmark_matrix/fleet/`. It is distinct from `PLAN.md`
> (the build roadmap) and `REQUIREMENTS.md` (the FRs). For the build status / next steps see
> `NEXT_STEPS.md`; for the design rationale of each slice see the corpus (`JOURNEY_DESIGN.md`,
> `FRONTEND_OPENAPI_CONTRACT.md`, `CONTAINERIZATION_SCOPING.md`, `COMPOSE_FLEET_PROTOTYPE.md`).

---

## 1. What it measures

Round 3 is a **system-level** benchmark: can a model build a *working, integrated* 9-service polyglot
microservice application (the Online Boutique demo), scored by a **real end-to-end user journey** over
the live system — not by static/structural signals on isolated files.

The headline metric is **weighted per-step journey coverage** with **honest per-service fault
attribution**: a model is credited for the journey steps its fleet completes, and a failure is charged
to the *responsible* service (never to a downstream service for an upstream break). A **decision gate**
then asks the two terminal questions of a round: *does the journey discriminate the finalists, and is
the attribution trustworthy?*

Design stance (why it discriminates — `Lessons_Learned/sdk/lessons/01-benchmarking.md` #5/#28):
**structural/compile/static signals saturate at the frontier; only executed behavior over a real
journey discriminates.** The harness runs the real app and drives the real journey.

---

## 2. The pipeline (M0 → M6 + the frontend bonus lane)

Each stage is a `fleet/` module + a `validate_mN.py` live entrypoint. All stages are macOS-Docker
runnable; every one is live-validated (see `NEXT_STEPS.md`).

| Stage | Module(s) | What it does |
|---|---|---|
| **M0** image build | `containerize.py` + `templates/Dockerfile.{go,python,node,csharp}.tmpl` | `build_service_image(service, workdir, language)` projects a generated service workdir into a runnable container image (per-language), reusing the behavioral offline-dep provisioning. `boot_and_probe` is **readiness-gated** — "ok" = the published port accepts a connection, not just that `docker run` returned an id (#31). |
| **M1** fleet | `services.py` + `compose.py` | `services.py` = the authoritative OB topology (8 backends + redis-cart, with `(listen_port, dial_port)`, dep edges, the email port-asymmetry + redis-sidecar traps). `compose.py` projects it into a docker-compose on an `internal: true` `fleet` network (network-layer **egress-deny** + service-DNS), wiring each `*_SERVICE_ADDR` dep edge. |
| **M2** journey + Adapter B | `journey.py` + `adapter_b.py` | The transport-agnostic 5-step journey (defined once) + the **direct-gRPC** driver that replays its fan-out against the live fleet, scoring each step. |
| **M3** scoring | `score.py` | `score_journey(JourneyResult) → Scorecard`: per-step coverage + **per-service fault attribution** + journey-completed + confidence. |
| **M4** frontend bonus | `frontend_contract.py` + `frontend_gate.py` + `frontend_reference/` | A Go HTTP→gRPC frontend + the health/contract **gate** + canonical **substitution** + **Adapter A** (HTTP driver). |
| **M5** bonus scoring | `report.py` | The frontend bonus folded into the report as a **capped, additive** column — never the rank key. |
| **M6** report + gate | `report.py` + `roster.py` + `round3.py` | Rank finalists, render `round3-system-report.{json,md}`, the advisory **decision gate**. CLI: `startd8 benchmark-round3`. |

The benchmark **measures model skill**: the deterministic-codegen + micro-prime SDK leverage is OFF;
each finalist's fleet is the model's own generated services.

---

## 3. The journey (the unit of measurement)

`journey.py` defines the canonical 5-step journey ONCE, transport-independently (JOURNEY_DESIGN §2.1),
weighted by the §1 locust task mix. Both adapters reproduce the same steps + payloads; only the
*encoding* differs (gRPC message vs HTTP form). The same `CheckoutPayload` (future-dated card) is reused
verbatim.

| # | Step | Weight | Services exercised | Expected outcome |
|---|---|---|---|---|
| 1 | **browse** | 10 | productcatalog, currency | products returned; a price renders in the active currency |
| 2 | **setCurrency** | 2 | currency | a whitelisted code is accepted |
| 3 | **addToCart** | 2 | productcatalog, cart | the item is in the cart |
| 4 | **viewCart** | 3 | cart, productcatalog, currency, shipping | cart shows the item; a shipping quote + total compute |
| 5 | **checkout** | 1 | **checkout** → its 6 deps | an order id is returned; the 6-dep PlaceOrder orchestration succeeds |

**Why weighted:** the browse-heavy mix means a catalog break (browse=10 + addToCart=2 + checkout=1) is
far more damaging than a payment break (checkout=1 only). Live, this scored `reference` 1.000 >
`no-payment` 0.944 > `no-catalog` 0.278 — the weighting discriminates as the real traffic mix intends.

### Two adapters (the journey, two transports)

- **Adapter B** (`adapter_b.py`, always-on diagnostic) — a direct-gRPC driver replaying the §1 fan-out
  against the live fleet from inside a driver container on the `fleet` network (dials by service-DNS,
  egress-deny preserved). The contestant **backends** are scored over this path.
- **Adapter A** (`frontend_gate.run_journey_http`, the frontend lane) — the form-encoded HTTP
  locust-mix driver, runs unchanged over either the generated or the canonical frontend (the HTTP
  contract is the substitution seam).

---

## 4. Scoring + per-service attribution (`score.py`)

A `Scorecard` carries:

- **Per-step coverage** — `weighted_coverage` (the headline, by the locust mix) + `unweighted_coverage`.
- **Per-service fault attribution** — each failed step names a **culprit** service; the scorer
  classifies it:
  - `model-fault` — the service's own code failed (its RPC errored / its response violated an
    invariant). This is what a model is charged for.
  - `propagated` — an **orchestrated** step's entry service (checkout) failed because a **downstream
    dep** broke; the entry is **NOT** charged model-fault, the dep is.
  - `harness` — a failed step with no identified culprit (treated as infra, not a model fault).
- **`journey_completed`** — did the checkout step pass.
- **`confidence`** — `low` when *every* step failed (no healthy baseline to attribute against).

**The load-bearing rule:** *a downstream break is never charged to the entry service.* Attribution
needs no separate health-probe pass — the journey's early DIRECT steps double as per-service liveness
signals, and the checkout orchestrator wraps each dep's error (`charge:`→payment, `getproduct:`→catalog)
so a checkout failure names the failing dep (#34). Validated live on broken meshes: break payment →
`model-fault: payment` + `propagated: checkout via payment`; break catalog → `model-fault: catalog` +
checkout propagated. The **known-broken-mesh tests are the attribution gate** (a mis-attribution
silently blames the wrong model).

---

## 5. The frontend bonus lane (M4/M5) — judged but never contingent

The 10th, **bonus** frontend service can never zero a model (`Lessons_Learned` #29). A
health/contract **gate** (`frontend_gate.run_gate`) runs the generated frontend against a **known-good
backend fleet** through escalating stages:

1. **BOOT** (blocking) — binds + `GET /_healthz` → 200.
2. **ROUTES** (blocking) — each gated route returns an acceptable status; malformed add/checkout → 4xx.
3. **JOURNEY** (blocking, **decisive**) — a real stateful one-session HTTP journey that must yield a
   **real order id**. Route-presence saturates; only this discriminates a subtly-broken frontend (a
   confirmation page *without* a real order id) — lean strict.
4. **ORCHESTRATION** (advisory) — observed fan-out fidelity → the bonus score.

**Verdict → action:** PASS (stages 1–3) → mount the generated frontend, award the bonus per
orchestration fidelity. FAIL → **substitute the canonical upstream frontend** (wired to the contestant
backends), record `frontend=canonical-substituted` + the failing stage, bonus = 0. **Backend scoring is
unaffected** either way. Live-proven: a `FRONTEND_BREAK_ORDER_ID` frontend fails at JOURNEY → substitute
→ Adapter A completes over canonical.

**M5 bonus folding (`report.py`):** `frontend_bonus = fidelity × FRONTEND_BONUS_CAP`, 0 unless the gate
passed. It is a **separate column**, never folded into `system_score` (the rank key) — ranking stays by
backend score; the bonus is a capped `+frontend` tie-break that breaks ties only among *equal* backends
(OQ-J3: a brilliant frontend can never lift a weak backend's rank).

---

## 6. The system report + decision gate (M6)

`report.py` ranks finalists by **backend system score** (weighted coverage; tie-break: fewer own
model-faults → higher frontend bonus → lower cost) and renders `round3-system-report.{json,md}` with
per-step coverage, attribution, journey-completed, confidence, the `+frontend` bonus column, and
cost/speed columns.

The **decision gate** (advisory, FR-21 — no auto-orchestrator) summarizes the two terminal questions:

> **GO iff the journey DISCRIMINATES the finalists (real score spread) AND the attribution is
> TRUSTWORTHY (the broken-mesh checks attribute to the right service+class).**

A finalist whose fleet can't be scored (images missing / won't boot) degrades **infra-honestly** (zero
coverage, low confidence, NO service charged model-fault) — a missing build is an environment outcome,
never a model's catastrophic 0.

---

## 7. Faithfulness + isolation properties

- **Network-layer egress-deny** — the `fleet` network is `internal: true`; backends reach each other by
  service-DNS but **cannot egress** (a contestant service can't phone home). Proven live (egress to
  `1.1.1.1:443` DENIED).
- **The two faithfulness traps** are encoded in `services.py` (so they can't be silently dropped):
  emailservice's `listen 8080 / dial 5000` port asymmetry, and the **redis-cart** infra sidecar
  cartservice needs. Both validated live.
- **Untrusted code** is built at **provision time** (network-allowed build stage) and **served** under
  the egress-denied fleet — scripts-disabled, deps vendored/curated.
- **infra-vs-model** — a missing key / dead provider / absent image is `infra_fail`, excluded from
  scores; never the model's 0.

---

## 8. How to run it

```bash
# The full round (advisory) — score each finalist's fleet, render the report + decision gate:
startd8 benchmark-round3 --roster roster.yaml --out ./round3-out
#   roster.yaml: finalists: [{model: <id>, image_namespace: r3/<id>}, ...]
#   omit --roster for the single SDK-reference finalist (self-test)

# Per-stage live validation (macOS Docker), each reusable + idempotent (build-if-missing):
PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m0 <go|python|node|csharp|shipping|currency>
PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m1 --subset checkoutservice,recommendationservice
PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m2   # Adapter B: 100% + break-payment attribution
PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m3   # score on reference + 2 broken meshes
PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m4   # frontend gate + substitution + Adapter A
PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m6   # end-to-end system report capstone
```

**Effectiveness practices baked in** (Mottainai / build-if-missing — runs reuse already-built images;
readiness-gated boot; `--subset` quick mode; the `compose stop <svc>` + driver `--no-deps` broken-mesh
generator). The full fleet is ~8 images + a Go frontend; a re-run reuses them all.

---

## 9. Module map (the shipped surface)

```
src/startd8/benchmark_matrix/fleet/
  services.py          # OB topology inventory (8 backends + redis; (listen,dial); deps; 2 traps)
  compose.py           # N-service compose-fleet generator (internal egress-deny net + service-DNS)
  containerize.py      # build_service_image + readiness-gated boot_and_probe + Dockerfile templates
  journey.py           # the defined-once 5-step transport-agnostic journey + canonical payload
  adapter_b.py         # direct-gRPC journey driver (per-step coverage + culprit attribution)
  score.py             # score_journey → Scorecard (coverage + attribution + completed + confidence)
  frontend_contract.py # the HTTP contract + gate stages + capped bonus model (the substitution seam)
  frontend_gate.py     # run_gate (boot/routes/journey/orchestration) + run_journey_http (Adapter A)
  report.py            # FinalistScore + ranking + decision gate + system-report render
  roster.py / round3.py# finalist roster + the round orchestration (behind `startd8 benchmark-round3`)
  validate_m{0,1,2,3,4,6}.py  # per-stage live entrypoints
tests/unit/benchmark_matrix/behavioral/fixtures/
  {catalog,checkout,shipping}_reference/   (Go)   {payment,currency}_reference/ (Node)
  {email,recommendation}_reference/ (Python)  cart_reference/ (C#)  frontend_reference/ (Go HTTP)
```

Java/adservice, kind/k8s, offline `--network=none`, and amd64 CI images are **deferred** (PLAN §Deferred).
