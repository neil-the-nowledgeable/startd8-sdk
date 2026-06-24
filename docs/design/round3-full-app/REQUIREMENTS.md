# Round 3 — Full 9-Service Application Round — Requirements

**Version:** 0.3 (Re-substrated to containers + folded in the post-v0.2 design corpus)
**Date:** 2026-06-24
**Status:** Reconciled to PLAN.md v0.3. The v0.2 netns/Seatbelt-fleet substrate framing is **SUPERSEDED** (verdict B overturned — see §0′); the fleet now runs on a container substrate (compose/kind), and the now-decided containerization / transport-agnostic journey / frontend-bonus / layered-scoring requirements are folded in. No code yet.
**Owner SDK area:** `startd8.benchmark_matrix` (a new Round-3 "system" harness) + a NET-NEW `benchmark_matrix.containers` build layer + `startd8.deploy_harness` (reuse) + `startd8.benchmark_matrix.behavioral` (suite/stub/sandbox reuse) + seeds.
**Parents:**
- `docs/design/benchmark-scoring/FUNCTIONAL_CORRECTNESS_TRACK2_EXPANSION_REQUIREMENTS.md` (the per-service behavioral frontier; defines NR-X1 live full-mesh + NR-X2 generated-deps as **out of scope** there)
- `docs/design/local-deploy-harness/LOCAL_DEPLOY_HARNESS_REQUIREMENTS.md` (the shipped graded deploy ladder)
- `docs/design/model-benchmark/` (Summer 2026 benchmark; Rounds 1–2)
- `docs/design/round3-full-app/CONTAINMENT_SPIKE.md` (the M1 feasibility gate — verdict B **OVERTURNED** by the §0 VERIFIED CORRECTION; container fleet + netns per-service)
- `docs/design/round3-full-app/COMPOSE_FLEET_PROTOTYPE.md` (the validated container substrate), `CONTAINERIZATION_SCOPING.md` (`build_service_image` + lanes), `JOURNEY_DESIGN.md` v0.2 (transport-agnostic journey + 2 adapters), `FRONTEND_OPENAPI_CONTRACT.md` + `FRONTEND_LANE_SCOPING.md` (frontend bonus + canonical substitution)
- `docs/design/round3-full-app/PLAN.md` v0.3 (the consolidated M0..M6 roadmap this doc is reconciled to)

---

## 0′. Supersession note (v0.3 re-substrates the fleet — traceable, not silent)

v0.3 records ONE load-bearing reversal plus folds in the post-v0.2 design corpus. The reversal is kept
**traceable**: superseded v0.2 text below is marked `~~struck~~`/labelled SUPERSEDED rather than deleted,
so the decision record survives.

> **SUPERSEDED — the v0.2 "verdict B / no-Docker / Seatbelt shared-loopback fleet" substrate.**
> CONTAINMENT_SPIKE.md §0 (VERIFIED CORRECTION, 2026-06-24) overturned verdict B for the fleet: OB
> services dial each other over **gRPC**, and under the macOS Seatbelt loopback profile **sandboxed gRPC
> dial-out is DENIED** — the only Seatbelt rule that lets gRPC dial (`remote ip "*"`) re-opens full
> external egress. **No Seatbelt profile permits sandboxed gRPC loopback dial-out while denying egress.**
> Therefore v0.3 re-substrates:
> - **The FLEET runs on a CONTAINER substrate** (docker-compose first, **kind** later), NOT a
>   netns/Seatbelt process fleet. Compose `internal: true` gives gRPC-over-service-DNS **and**
>   network-layer egress-deny simultaneously (COMPOSE_FLEET_PROTOTYPE.md, LIVE-VALIDATED on macOS Docker).
>   **Network-layer egress-deny + default container hardening are KEPT** for the untrusted generated services.
> - **netns is RETAINED but RE-SCOPED:** it is the Linux substrate for **per-service SANDBOXED dial-out
>   scoring** (checkout's 6 stubs, recommendation's 1 stub — Round 2's latent macOS gap), NOT the fleet.
>   `netns_substrate.py` is LIVE-VALIDATED on Linux (real gRPC channel ready + egress denied).
> - **FR-7a's shared-loopback weakening is RE-SCOPED:** it now applies **only to the non-sandboxed
>   dial-out fallback on macOS** (where Seatbelt cannot deny egress for dial-out SUTs), **NOT** to the
>   network-contained container fleet. The container fleet has structural network-layer containment and
>   **no shared host loopback plane**, so the v0.2 "one unrestricted 127.0.0.1 loopback plane" weakening
>   does not apply to it.
> - OQ-6 (containment) flips from "RESOLVED → verdict B, no Docker" to **"RESOLVED → container substrate"**;
>   OQ-7 (Linux substrate) is **no longer an optional follow-up** — netns is the REQUIRED Linux substrate
>   for per-service sandboxed dial-out (validated), and kind is the deferred max-fidelity fleet substrate.

**Decisions LOCKED across the corpus (carried, NOT re-opened by v0.3):** single-model fleet (OQ-1);
layered scoring = per-step coverage headline + per-service fault attribution + derived "journey completed"
boolean (OQ-2); manual finalists / advisory report, no auto-tournament (FR-21/NR-1/NR-7); Java/adservice +
kind deferred to v2. v0.3 changes the **substrate** and **adds** containerization/journey/frontend-bonus/
layered-scoring FRs; it does **not** re-litigate the locked topology/scoring decisions.

---

## 0. Planning Insights (Self-Reflective Update)

The planning pass (reading the shipped `deploy_harness`, `behavioral` harness, and seeds) plus the **containment spike** (CONTAINMENT_SPIKE.md) resolved the two load-bearing forks and the security feasibility gate. Highlights:

| v0.1 assumption | Finding (planning + spike) | Impact |
|---|---|---|
| Build topology was an open fork (single-model vs best-of-breed vs hybrid). | Best-of-breed **recreates** the cross-model confound NR-X2 forbids (a great checkout scored badly because *another* model's payment is broken) — answers an ecosystem question no model tournament asks. | **OQ-1 RESOLVED → single-model fleet.** Each candidate builds all 9; its own fleet is deployed + scored as that model's system. Best-of-breed allowed only as an opt-in **diagnostic** view, never the headline. Topology FR (FR-15) now mandates single-model. |
| Scoring was an open fork (full-system pass/fail vs step credit vs per-service-in-integration). | Pure full-system pass/fail is **brutally lossy** — one weak service (e.g. email) zeros a finalist with 8 perfect services. | **OQ-2 RESOLVED → layered scoring.** Headline = per-journey-step coverage; PLUS per-service fault attribution; PLUS a derived boolean "canonical journey completed" flag. FR-13/14/16 updated. |
| Docker-per-service might be a hard prerequisite for co-running 9 untrusted servers. | ~~Spike **verdict B (MEASURED):** macOS Seatbelt is per-process; N sandboxed servers co-exist, a peer is reachable over loopback, egress stays DENIED.~~ **SUPERSEDED (see §0′):** verdict B held only for a **raw socket**; OB peers dial over **gRPC**, which Seatbelt DENIES on loopback unless egress is re-opened. | **RE-SUBSTRATED (§0′): the fleet runs on a CONTAINER substrate** (compose `internal: true` → gRPC-over-service-DNS + network-layer egress-deny, validated on macOS Docker). netns is re-scoped to per-service Linux dial-out scoring. The new work is the per-language image builder + N-service compose-fleet generator. |
| Multi-service isolation is "best-effort, recorded honestly" (vague). | Spike pinned the exact weakening: the fleet shares **one unrestricted 127.0.0.1 loopback plane** → a compromised/buggy service can reach **any** sibling or host loopback port, not just its declared deps. | **FR-7a now records this honestly + ACCEPTED** (all 9 are same-model output on a disposable host) with named mitigations + a concrete **escalation trigger → Docker (option C)**. |
| The shipped deploy harness is the Round-3 foundation. | **Only a partial foundation.** `deploy_app_local` is single-app/single-venv/single-port; `deploy_batch` deploys roots **independently and serially**, never together; `context_smoke` dials *pre-existing remote* producers, never *stands up* a fleet. | Deploy harness contributes **discovery + Python venv/install + readiness/health patterns**; the **co-deploy + inter-wiring is net-new** (the load-bearing FR-4/5/6 fleet orchestrator). |
| Isolation behaves the same everywhere. | Spike found the substrate is **platform-dependent**: on Linux CI the sandbox auto-selects `unshare -rn` (per-netns), which **removes** the FR-7a weakness but **breaks** shared-loopback peer reachability — so a Linux fleet needs a shared-netns / veth design. | v1 targets **macOS-style shared loopback**; a Linux fleet substrate is a **follow-up design** (NEW open question OQ-7 below), not resolved here. |

### Resolved open questions
- **OQ-1 (build topology) → SINGLE-MODEL FLEET.** Each candidate model builds all 9 services; its own fleet is deployed together and scored as that model's system. Best-of-breed REJECTED as the headline (recreates the NR-X2 cross-model confound); permitted only as an opt-in diagnostic view.
- **OQ-2 (scoring/attribution) → LAYERED.** Headline = per-journey-step coverage; PLUS per-service fault attribution; PLUS a derived boolean "canonical journey completed" flag. Pure full-system pass/fail REJECTED as the sole metric.
- ~~**OQ-6 (multi-service containment) → VERDICT B (no Docker in v1).**~~ **SUPERSEDED → CONTAINER SUBSTRATE (§0′).** Verdict B was overturned (gRPC dial-out denied under Seatbelt). The fleet now runs on docker-compose (`internal: true` → service-DNS gRPC + network-layer egress-deny, validated); netns is re-scoped to per-service Linux sandboxed dial-out scoring. FR-7a's weakening is re-scoped to the macOS non-sandboxed dial-out fallback only.

### NEW open question (left open)
- **OQ-7 (NEW — Linux fleet isolation substrate).** The isolation substrate is **platform-dependent**. v1 targets the **macOS Seatbelt shared-loopback** plane (FR-7a). On Linux CI the sandbox auto-selects `unshare -rn` (per-netns), which removes the FR-7a weakness **but breaks shared-loopback peer reachability** — peers in separate netns cannot dial each other's `127.0.0.1`. A Linux fleet therefore needs a **shared-netns / veth-bridge design** (e.g. run all 9 services in ONE shared network namespace). This is **deferred** to a follow-up design, **not resolved** in v1.

---

## 1. Problem Statement

Rounds 1–2 measure a model on **one service at a time**, dependencies **mocked/stubbed**, each cell isolated, so a failure is cleanly attributable to that model on that service. Round 3 — the tournament's **final round** — measures something Rounds 1–2 deliberately cannot: **can a model build a working *system*?** Each finalist builds **all 9 Online Boutique services**, they are **deployed together**, and **real cross-service user journeys** (browse → add-to-cart → checkout → payment → confirmation) run against the live mesh.

This crosses two frontiers the per-service design explicitly fenced off:
- **NR-X1** (live full-mesh OB — all real services co-running)
- **NR-X2** (a service dialing **another model's generated** dependency, not an SDK stub)

The per-service design fenced these off because they **confound attribution**: if checkout's deps were generated, checkout's score would absorb its deps' quality. Round 3 *wants* this confound for the system verdict, but must be honest that a single weak service can zero an entire journey. **The build topology and the scoring/attribution model are therefore the two fundamental forks** (OQ-1, OQ-2 below) and the rest of the spec is conditional on them.

### What exists vs what Round 3 needs

| Component | Current state (grounded in code) | Gap for Round 3 |
|---|---|---|
| Per-service behavioral scoring | `behavioral/execute.py` `_SUITES`, `run_service_sandboxed` (one sandboxed SUT, loopback client, guaranteed teardown) | Scores **one** service against **SDK stubs**, never a peer generated service |
| Orchestrator-with-deps primitive | `_run_checkout_cell` brings up 1 SUT + injects 6 `*_SERVICE_ADDR` env + tears down on every path | Deps are **SDK stubs** (`CheckoutStubHarness`), not 8 generated peer services; only 1 SUT process |
| Deploy ladder | `deploy_harness.deploy_app_local` — discover→install→boot→health→smoke for **one app root**, one venv, one port | No multi-service co-deploy; `deploy_batch` deploys roots **independently & serially**, not **together** |
| Cross-context smoke | `context_smoke.run_outbound_context_smokes` dials remote producers by resolved `base_url` | Producers are pre-existing/remote; no mechanism to **stand up** the producer fleet first |
| Seeds | 9 OB backend services (`seeds-index.json`), shared `demo.proto`, per-service `startup` blocks (checkout has one; cart/catalog/recommendation/email being added in Track-2 expansion) | **No `frontend` and no `loadgenerator` seed** — the "user journey" driver does not exist as a seed |
| Cross-service journey | none | A browse→cart→checkout→payment→confirm journey + its system-level ground truth must be SDK-authored |
| Scorecard | `aggregate.py` per-service `functional_median`/leaderboard | No "system result" cell kind or per-journey surfacing |

---

## 2. Goals & Non-Goals

**Goals**
1. Stand up a **fleet** of generated OB services together on loopback, wired to each other by injected `*_SERVICE_ADDR` env (generalizing `_run_checkout_cell`), and run **SDK-authored cross-service journeys** against the live mesh.
2. Produce a **system-level result** per candidate with **honest attribution** — distinguish "the model's checkout is broken" from "the model's payment is broken and checkout merely propagated it."
3. **Degrade honestly:** a service that won't boot, a journey step that can't run, or a toolchain gap must degrade with a typed reason and be visible in the report — never a silent system 0 attributed to the wrong service.
4. **Reuse, not rebuild:** the deploy ladder, the sandbox (`run_service_sandboxed`), the `*_SERVICE_ADDR` injection pattern, the gRPC suite clients, durable per-cell persistence, and the leaderboard.
5. Operate as a **human-curated** final round: the user picks the ~4 finalists; no auto-orchestrator selects them (NR-7).

**Non-Goals**
- Auto-selecting finalists from earlier rounds (NR-7 — manual).
- Load/perf/soak/chaos testing of the mesh.
- Kernel-level isolation beyond the inherited host controls (parent NR-T2-2). **v0.3 update:** the fleet's containment is now **network-layer** (container `internal: true` network egress-deny + default container hardening), not the v0.2 Seatbelt loopback plane (§0′). The macOS non-sandboxed dial-out fallback weakening is recorded in FR-7a; per-service sandboxed dial-out scoring uses netns on Linux.
- A real browser/HTML frontend or a generated `loadgenerator` (the journey driver is an SDK-authored gRPC/HTTP client unless OQ-5 says otherwise).
- Real external persistence backends (Redis/Spanner) unless a journey demands provisioned state (inherits per-service state-fixture approach).

---

## 3. Requirements

### Fleet build & roster (depends on OQ-1)
- **FR-1** Round 3 operates on a **finalist set** the user supplies explicitly (model ids), not a computed selection (NR-7).
- **FR-2** Under the **single-model-fleet** topology (OQ-1 RESOLVED), each finalist must have a build of **all 9 services** — every service in the mesh is that same finalist's build. The harness sources each service's generated workdir from that model's prior per-service runs (the durable batch roots) keyed by **verbatim model id** (reuse `deploy_harness.batch._read_model_id` sidecar convention), or re-generates the missing ones. **FR-2a:** a finalist missing service S degrades that finalist's journeys touching S **with the reason "service-missing:S"**, never a silent 0.
- **FR-3** The roster of 9 is the OB backend set in `seeds-index.json` (cart, productcatalog, currency, shipping, payment, email, checkout, recommendation, ad). **FR-3a:** services not on any journey path (ad, recommendation, email-as-sink) are deployed-but-optional — their absence degrades only the journeys that touch them.

### Multi-service deployment (net-new — the core capability)
- **FR-4** A **fleet deployer** brings up N generated services **together** on distinct free loopback ports, computes the **dependency-address env map** (`{SERVICE}_SERVICE_ADDR → 127.0.0.1:<port>`) for the whole mesh from `demo.proto` service→dependency edges, and injects each service's required addresses **before it launches** (generalize `_run_checkout_cell` steps b–d to a topologically-ordered fleet).
- **FR-5** Bring-up is **dependency-ordered** (leaf services first; checkout last), each gated on a **readiness probe** (reuse `run_service_sandboxed` readiness; tcp/http per seed `startup.readiness`). A service that never becomes ready degrades the fleet with `service-not-ready:S` and the report records which journeys are thereby unrunnable.
- **FR-6** **Guaranteed teardown of the whole fleet** on every exit path (success, any service launch/readiness failure, journey exception) — no orphaned listeners/process groups (generalize the `finally: harness.stop()` discipline; reuse the process-group kill in `sandbox.py`).
- **FR-7** (RE-SUBSTRATED — §0′). The fleet runs on a **container substrate**: each generated service is built into its own image and co-run as a container on an **internal, egress-denied** network (docker-compose `internal: true` first, **kind** + `NetworkPolicy` later). Containment is **structural and network-layer** — a backend container has **no route off the fleet network** (no gateway), so external egress is denied by construction while peers dial each other over **service-DNS gRPC**. Default container hardening is **KEPT** for the untrusted generated services. ~~SUPERSEDED v0.2: "each service runs under the same Seatbelt single-SUT controls; no Docker layer required in v1" — verdict B was overturned (gRPC dial-out denied under Seatbelt loopback, §0′).~~ Per-service SANDBOXED dial-out *scoring* (checkout/recommendation) — distinct from the fleet — uses **netns** (`unshare -rn` shared-netns) on Linux, where gRPC-loopback + egress-deny co-exist (validated); on macOS that per-service path degrades to the non-sandboxed fallback (FR-7a).
- **FR-7a** (containment weakening — RE-SCOPED + recorded + ACCEPTED). **This weakening now applies ONLY to the non-sandboxed dial-out fallback on macOS, NOT to the container fleet.** The network-contained container fleet (FR-7) has **no shared host loopback plane** — the v0.2 "one unrestricted 127.0.0.1 loopback plane" weakening **does not apply to it**. The residual weakening is narrow: on **macOS**, a **per-service** sandboxed *dial-out* SUT (checkout/recommendation) cannot be both gRPC-dial-capable and egress-denied under Seatbelt (§0′), so on macOS it runs **non-sandboxed** (egress NOT denied for that one SUT) — captured in provenance, not hidden. **ACCEPTED** because it is per-service (not the fleet), same-model output, on a disposable host. **Mitigations (required):** (i) prefer the **container fleet** (egress-denied by construction) for full-mesh scoring; (ii) use **netns on Linux** for sandboxed per-service dial-out scoring (egress denied + gRPC works, validated); (iii) keep secrets out via existing `scrub_env`; (iv) no sensitive host service listening during a macOS non-sandboxed run. **Escalation trigger:** mixing services from **different models/tenants** in one fleet, or a **non-disposable host** — forces the container substrate (already the v0.3 default) or netns-per-service. See CONTAINMENT_SPIKE.md §0 and OQ-7.
- **FR-7b** (NEW — per-service container image build). Each generated service is turned into a runnable container image by a harness-owned `build_service_image(service, workdir)` (`benchmark_matrix.containers`): it stages the generated source + the existing **offline** dep closures (`setup_go_stubs` / `.pydeps` / node closure / `publish_dotnet_service`) + the OB gRPC stubs into a per-language Dockerfile build stage, deriving the container `CMD` from `contract.resolve_serve_command`. **Offline build is a hard requirement** (no network at build or run; mirror the digest-pinned multi-arch upstream Dockerfiles as reference patterns, not drop-ins). Go/Python/Node are the ~80% reuse lanes; **C# requires a warm-NuGet bake** (the one load-bearing offline gap — `dotnet restore` is the only network step; bake+snapshot `~/.nuget` then `--no-restore` publish). Java/adservice container build is **deferred** (v2; the only language with zero offline-build support — degrade honestly per FR-8).
- **FR-7c** (NEW — N-service compose-fleet generator). A fleet generator emits a docker-compose (generalizing the validated 2-service `compose-prototype`) standing up all 8 (v1) / 9 backends together: one container per service on an `internal: true` `fleet` network (network-layer egress-deny), each service's `*_SERVICE_ADDR` deps injected as `service-name:port` from the startup contracts, **dependency-ordered readiness** bring-up, and **guaranteed `compose down -v --remove-orphans` teardown** on every exit path. It must encode the two faithfulness traps: emailservice's **port asymmetry** (`listen 8080 / dialed 5000`) and the **redis-cart** infra sidecar cartservice requires (a non-seed infra dependency, JOURNEY_DESIGN §3). Keep `*_SERVICE_ADDR` wiring **substrate-parameterized** so the same driver runs over compose now and kind later (OQ-C7).
- **FR-8** The fleet deployer is **polyglot**: it builds/launches C# (cart), Go (catalog/checkout/shipping), Node (currency/payment), Java (ad — deferred v2), Python (recommendation/email) services via `build_service_image` (FR-7b) + the container CMDs derived from `resolve_serve_command`, degrading honestly per service where a toolchain/offline-build is genuinely absent (FR-32 inheritance). Java/adservice degrades (no offline build yet) without zeroing the fleet (FR-3a — ad is off the journey).

### Cross-service journeys & ground truth
- **FR-9** Define the canonical journey **ONCE as a transport-agnostic spec** (JOURNEY_DESIGN.md v0.2 §2.1): the 5 logical steps **browse → setCurrency → addToCart → viewCart → checkout** with **transport-independent expected outcomes**, derived from the canonical `loadgenerator/locustfile.py` mix (`browse` 10, `viewCart` 3, `setCurrency`/`addToCart` 2, `index`/`checkout` 1) and the 9-SKU fixture set + future-dated checkout payload. Step inputs are reused **verbatim** by both adapters (FR-9a/9b); only the *encoding* differs. ~~SUPERSEDED v0.2: a single SDK-authored gRPC client sequence — v0.3 splits this into a transport-agnostic spec run over two adapters.~~
- **FR-9a** (NEW — Adapter B, direct-gRPC, always-on diagnostic backbone). An SDK-authored driver replays the journey fan-out directly against the contestant backends' gRPC endpoints (reusing the validated `checkout_suite`/`*_suite` client machinery + the 6-dep PlaceOrder path against **live contestant backends**, not stubs). It is **contestant-pure** (no reference code in the measured surface) and is **always run** — it isolates whether the backends *compose*, independent of any frontend. It owns the orchestration the frontend would normally own (proves composition, not HTTP→gRPC translation).
- **FR-9b** (NEW — Adapter A, HTTP, canonical journey). The form-encoded HTTP journey (the locustfile mix) run end-to-end against **whichever frontend is in place** (generated if it passes the gate, else canonical — FR-23). Because both frontends satisfy the **same journey-facing HTTP contract** (FRONTEND_OPENAPI_CONTRACT.md, the substitution seam), the Adapter-A driver runs **unchanged** over either. This is the literal OB data path (real HTTP surface + real HTTP→gRPC fan-out).
- **FR-10** Each journey carries **SDK ground truth** (the oracle): the expected order total = Σ(price×qty) currency-converted + shipping, non-empty tracking_id/transaction_id, cart emptied post-order, etc. — promote the `CheckoutStubHarness.GroundTruth` oracle math to a **fleet-level oracle** that knows the seeded catalog/cart fixtures.
- **FR-11** Journeys must be defined as an **ordered list of steps**, each step attributable to the **service that owns it** (browse→catalog, convert→currency, …), so a step failure names a responsible service (feeds attribution, OQ-2).
- **FR-12** State the **catalog/cart fixtures** the journey assumes (reuse the Track-2 expansion `products.json` state-fixture mechanism); the journey cannot assert against an unknown catalog.

### Scoring & attribution (depends on OQ-2)
- **FR-13** Produce, per finalist, a **layered system result** (OQ-2 RESOLVED), NOT a single pass/fail. Three layers: **(headline) per-journey-step coverage** — fraction of journey steps that passed, so partial credit survives one broken service; **(attribution) per-service fault attribution** — which service caused each failed/degraded step (FR-14); **(derived) a boolean "canonical journey completed" flag** — did the full browse→checkout→confirm journey complete end-to-end. The boolean is reported but is **not** the sole/headline number (pure full-system pass/fail REJECTED — one weak service would zero a finalist with 8 perfect services).
- **FR-14** **Attribution honesty (the core requirement):** every failed/degraded step records the **owning service** and a **fault class**: `model-fault:S` (S's own service produced a wrong/missing result), `propagated:S←D` (S behaved correctly given a broken upstream D), `degraded:S` (S unrunnable — missing/won't-boot/toolchain), or `harness`. A downstream service must **not** be charged a model-fault for a fault originating upstream (mirror the per-service `model_fault` vs `degrade` discipline; generalize across the mesh).
- **FR-15** **Topology = single-model fleet (OQ-1 RESOLVED); no cross-model dependency mixing in the headline result.** Each candidate model builds all 9 services; its **own** fleet is deployed together and scored as that model's system. Every service in a finalist's mesh is **that same finalist's** build, so a journey score is attributable to one model — this is how Round 3 *honors* the spirit of NR-X2 while crossing the frontier (the confound is *within one model*, not *across models*). Best-of-breed (mixing each model's best per-service build) is **REJECTED as the headline** — it recreates the exact cross-model confound NR-X2 forbids — and is permitted **only as an opt-in DIAGNOSTIC view** (to localize whether a finalist's journey failure is its own checkout vs its own dependency), explicitly labeled non-attributable-to-one-model, with FR-14's `propagated` class mandatory in that mode.
- **FR-16** Roll up step coverage to a **journey pass-rate** and a **system score** per finalist (the headline layer), **weighted by the canonical locust mix** (browse 10 … checkout 1) and/or reported unweighted, and surface the derived **"canonical journey completed" boolean** alongside it; both surface alongside (not replacing) the Round-1/2 per-service leaderboard columns. Per-service fault attribution (FR-14) uses the `*_SERVICE_ADDR` call-counter to classify each failed step; the known-broken-mesh tests (break payment / break catalog → fault attributed to the right service with the right class, downstream never charged `model-fault` for an upstream break) are the attribution gate.

### Frontend BONUS service + canonical substitution (NEW — JOURNEY_DESIGN v0.2 / FRONTEND_*)
- **FR-23** (NEW — frontend is a BONUS service that can never zero a model). Add an optional **10th `frontend` service** (Go lane reuse, HTTP/HTML surface, dials the 7 journey gRPC backends). It is scored as **pure BONUS**: a model MAY generate it; failure is **contained by canonical substitution** so it never subtracts. **FR-23a — health + OpenAPI-contract gate:** a generated frontend must boot, serve the journey-facing routes, and **complete an end-to-end stateful checkout against a known-good (canonical) backend fleet** (the gate is **behavioral** — routes respond + journey completes — not a strict JSON-schema match; **lean strict**, the stateful end-to-end checkout is the decisive defense against a subtly-broken frontend, e.g. a confirmation page without a real order id). **FR-23b — canonical substitution:** gate FAIL (missing / won't boot / off-contract / checkout fails) → the harness **substitutes the canonical upstream `src/frontend`** wired to the contestant backends via `*_SERVICE_ADDR`, **cleanly (no partial mount)**; Adapter A (FR-9b) still runs over the canonical frontend so the HTTP journey + all backend scoring continue uninterrupted. The run report records **which frontend ran + gate verdict + reason** and a `frontend = generated | canonical-substituted` field. **FR-23c — graceful ad-degrade:** the frontend must tolerate a **missing adservice** (Java deferred) without failing the journey (ads non-critical — log-and-continue), which is what lets the frontend ship in a Java-deferred v1.
- **FR-24** (NEW — frontend bonus is additive + capped, never rank-flips backends). The frontend contributes (a) a frontend service score (route correctness + orchestration fidelity, gate-gated, **0 if absent/failed/substituted**) + (b) a `journey_via_generated_frontend` flag, folded into the scorecard as **separate columns** (`backend_score` ranked; `frontend_bonus` additive tie-break/annotation). The bonus is **capped** so it stays a tie-break and **never rank-flips the backend ranking** — a brilliant frontend over weak backends must never outrank a strong-backend model. A substituted run shows `frontend_bonus = 0`; the substituted-run `canonical_journey_completed` flag is an **authenticity** signal (the journey ran over reference code), **not** frontend bonus.

### Reuse of shipped infra
- **FR-17** Reuse `deploy_harness` discovery (entrypoint/deps/mode detection) and venv/install for the **Python** services; reuse `run_service_sandboxed` for the launch+readiness+teardown of **every** service. Do **not** rebuild install/boot/health.
- **FR-18** Reuse the `*_SERVICE_ADDR` env convention and `demo.proto`-derived dependency edges already encoded in the checkout seed `startup.dependency_addr_env`.
- **FR-19** Reuse durable per-cell persistence (R3-S1) and the join-by-verbatim-model-id sidecar (`deploy_harness.batch`) so a Round-3 system run is **persist-then-rescore** (Mottainai) — re-score a captured fleet for $0 as journeys/oracles improve.

### Scorecard surfacing
- **FR-20** Emit a Round-3 **system report** (`round3-system-report.{json,md}`): per finalist, per journey, per step — status + fault class + owning service; a fleet bring-up roll-up (which services booted/were-ready); a finalist leaderboard **ranked by `backend_score`** with cost/speed columns; and the **additive `frontend_bonus` column** + `frontend = generated|canonical-substituted` + gate verdict/reason (FR-23b/FR-24), as a labeled tie-break that never rank-flips the backend ranking (reuse aggregate.py patterns).
- **FR-21** The report must make the **integration frontier visible**: for each finalist, "deepest journey step reached" (analogous to `highest_stage`), so a finalist that builds 9 services that boot but never complete checkout is distinguishable from one that completes the full journey.

### Degrade honesty (cross-cutting)
- **FR-22** Any environment/toolchain/missing-service condition degrades **the specific affected steps** with a typed reason and is counted as `degraded`, never as a model-fault and never as a silent 0 (inherits FR-32). A run where **most** steps degrade must be flagged as low-confidence (no all-degrade masquerading as a system pass/fail).

---

## 4. Non-Requirements

- **NR-1** No auto-selection of finalists (manual; NR-7).
- **NR-2** (REVISED by v0.3) No real *browser* and no generated *loadgenerator*. **But** a generated `frontend` is now in scope as an optional **BONUS** HTTP service (FR-23), exercised by the SDK-authored Adapter-A HTTP driver; on gate failure the canonical upstream frontend is substituted. The journey driver remains SDK-authored.
- **NR-3** No load/perf/soak/chaos.
- **NR-4** No kernel isolation beyond inherited best-effort host controls (and Round 3 *weakens* the single-SUT story — recorded, FR-7a).
- **NR-5** No real external persistence backends unless a journey needs provisioned state (reuse fixtures).
- **NR-6** Round 3 does **not** re-implement per-service scoring; it composes services and scores the *system*.
- **NR-7** (inherited) No cross-model dependency mixing as the default — see FR-15/OQ-1.

---

## 5. Open Questions

> **Status after v0.3 re-substration:** OQ-1, OQ-2 stay **RESOLVED** (single-model fleet / layered scoring). **OQ-6 is SUPERSEDED → container substrate** (verdict B overturned, §0′). **OQ-7 is RESOLVED for the per-service path** (netns on Linux, validated) with the **kind fleet substrate deferred**. OQ-3/4/5 remain planning-resolvable. Retained below for the decision record.

### OQ-1 — Build topology — **RESOLVED → (a) single-model fleet** (best-of-breed = opt-in diagnostic only; see §0, FR-15)
How is the fleet composed?
- **(a) Single-model fleet** — one model builds all 9; the mesh is entirely that model's code; scored as a system. Attribution stays *within one model*.
- **(b) Best-of-breed** — mix each model's best per-service build into one mesh, then score integration. Measures the *ecosystem*, not a model.
- **(c) Hybrid** — single-model fleet for the system verdict, plus an *optional* best-of-breed "reference mesh" to isolate whether a finalist's journey failure is its checkout vs its dependency.

**Recommendation: (a) single-model fleet, with (c)-hybrid as an optional diagnostic.** Rationale: (a) is the only topology that keeps the result **attributable to a model** — which is the entire point of a model *tournament* and the spirit of NR-X2 (don't confound a model's score with *another model's* deps). (b) directly violates NR-X2's intent (a great checkout scored badly because someone else's payment is broken) and answers an ecosystem question nobody asked in a model tournament. (a) also maximizes reuse: the generated workdirs already exist per-model in the durable batch roots (FR-2). Keep (c) as an opt-in diagnostic only when a finalist's journey fails and we want to localize blame (swap one service for an SDK reference build), explicitly labeled.

### OQ-2 — Scoring / attribution model — **RESOLVED → (b) per-step coverage headline + (c) attribution + (a) derived "journey completed" boolean** (layered; see §0, FR-13)
How is a system verdict computed when one weak service can zero a flow?
- **(a) Full-system pass/fail** on the end-to-end journey (binary).
- **(b) Per-journey-step credit** — fraction of journey steps that passed, each step owned by a service.
- **(c) Per-service-health-within-integration** — score each service's behavior *as observed during the live journey* (e.g., did catalog return the right product when the real checkout called it).

**Recommendation: (b) per-journey-step credit as the headline, enriched with (c)'s attribution, and (a) reported as a derived "did the full journey complete" flag.** Rationale: (a) alone is brutally lossy and exactly the "one weak service zeros everything" failure the prompt flags — a finalist with 8 perfect services and a broken email would score the same as one that builds nothing. (b) gives partial credit and, combined with FR-14's fault classes, tells you *which* service broke and whether the break was that service's fault or propagated. (c) is the attribution mechanism, not a separate headline. (a) is still worth reporting as a single honest "completed the canonical journey: yes/no" bit because that *is* the user's original "can it build a working system" question — but it must not be the *only* number.

### OQ-3 — Where do the 9 generated services come from?
Re-generate all 9 per finalist in Round 3, or **reuse** the per-service workdirs already produced in Rounds 1–2 (joined by verbatim model id)?
- **Recommendation: reuse the durable per-service workdirs (Mottainai), re-generating only services a finalist lacks.** The batch roots already hold per-model workdirs with `.model` sidecars (FR-2/FR-19). Re-spending budget to regenerate what exists violates the project's Mottainai principle and inflates cost. Caveat to resolve in planning: Round 1/2 services were generated *in isolation against the proto* — they should already be mesh-compatible (same `demo.proto`, same `*_SERVICE_ADDR` convention), but this assumption must be verified in Phase 2.

### OQ-4 — The journey driver: SDK-authored client vs generated frontend — **REVISED by v0.3 → BOTH (two adapters), generated frontend promoted to BONUS**
- ~~Recommendation: SDK-authored gRPC client only; defer a generated-frontend variant (a generated frontend would be a 10th confounding service).~~ **REVISED (JOURNEY_DESIGN v0.2):** the journey is defined **once** (FR-9) and run over **two adapters** — Adapter B (SDK-authored direct-gRPC, always-on diagnostic, contestant-pure — FR-9a) **and** Adapter A (HTTP over a frontend — FR-9b). The generated frontend is no longer deferred/rejected: it is promoted to a **BONUS** service (FR-23) whose failure is contained by **canonical substitution** (FR-23b), so it can never confound or zero the journey. The SDK still owns the oracle/ground truth.

### OQ-5 — Email/side-effect & ad/recommendation steps in the journey
email returns `Empty` (no observable) and ad/recommendation aren't on the purchase path. Include them as journey steps?
- **Recommendation: keep email as a *call-counter* step inside checkout (reuse FR-CO-8 counter observable), and treat ad/recommendation as **optional browse-adjacent** steps that degrade-only (FR-3a) rather than gating the purchase journey.** Resolve final inclusion in planning against discrimination value.

### OQ-6 — Multi-service isolation containment (security) — ~~RESOLVED → verdict B, no Docker~~ **SUPERSEDED → CONTAINER SUBSTRATE** (§0′; CONTAINMENT_SPIKE §0 correction)
Running N untrusted servers concurrently and wired by gRPC weakens the single-SUT story. Docker/netns-per-service a hard prerequisite?
- ~~RESOLVED by the spike (verdict B): the existing Seatbelt sandbox suffices, no Docker in v1.~~ **OVERTURNED:** verdict B held only for a **raw socket**; OB peers dial over **gRPC**, which Seatbelt **DENIES** on loopback unless egress is re-opened (no profile gives gRPC-loopback + egress-deny together). **RESOLVED → the fleet runs on a CONTAINER substrate** (compose `internal: true` → service-DNS gRPC + network-layer egress-deny, validated on macOS Docker; FR-7/7b/7c). FR-7a's shared-loopback weakening is re-scoped to the macOS non-sandboxed per-service dial-out fallback only.

### OQ-7 — Linux substrate for per-service sandboxed dial-out — **RESOLVED (netns) for per-service; kind deferred for the fleet**
The isolation substrate is **platform-dependent**. ~~v1 targets the macOS Seatbelt shared-loopback plane (FR-7a).~~ Re-scoped by §0′:
- **Fleet:** docker-compose `internal: true` on the macOS dev host (validated); **kind** + `NetworkPolicy` is the **deferred** max-fidelity fleet substrate (the canonical OB is k8s-native, no upstream compose — kind is where compose converges). Keep `*_SERVICE_ADDR` wiring substrate-parameterized (OQ-C7).
- **Per-service sandboxed dial-out scoring** (checkout/recommendation): **netns** (`unshare -rn` shared-netns) on Linux is the **REQUIRED + VALIDATED** substrate — real gRPC channel ready + egress denied simultaneously (the exact combination Seatbelt cannot give). On macOS this per-service path degrades to the non-sandboxed fallback (FR-7a). Wiring `netns_substrate.run_cell_in_shared_netns` into the checkout/recommendation cells (closing Round 2's latent macOS dial-out gap) is **deferred** to Linux CI but no longer an open *design* question.

---

*v0.3 — re-substrated to containers + folded in the post-v0.2 corpus. OQ-1 (single-model fleet) + OQ-2 (layered scoring) stay locked; OQ-6 SUPERSEDED → container substrate (verdict B overturned); OQ-7 resolved for the per-service netns path (kind fleet deferred). The load-bearing build is now the per-language image builder + N-service compose-fleet generator + the two-adapter journey + the frontend BONUS lane.*

---

**Footer (v0.2 → v0.3 delta):**
- **§0′ supersession note added** — records the ONE load-bearing reversal (verdict B overturned: sandboxed gRPC dial-out denied under macOS Seatbelt → the fleet re-substrates to **containers** (compose/kind), netns retained but re-scoped to per-service Linux dial-out scoring). Superseded v0.2 text marked, not deleted.
- **FRs UPDATED/SUPERSEDED in place (ids stable): 4** — **FR-7** (Seatbelt fleet → container substrate), **FR-7a** (shared-loopback weakening re-scoped to the macOS non-sandboxed per-service dial-out fallback only), **FR-8** (polyglot launch via `build_service_image` + Java/ad deferred), **FR-9** (single gRPC sequence → transport-agnostic spec).
- **FRs ADDED: 7** — **FR-7b** (`build_service_image`, offline, per-language Dockerfiles + C# warm-NuGet), **FR-7c** (N-service compose-fleet generator + email port-remap + redis-cart traps), **FR-9a** (Adapter B direct-gRPC always-on), **FR-9b** (Adapter A HTTP), **FR-23** (frontend BONUS + health/OpenAPI gate + canonical substitution), **FR-24** (additive capped frontend bonus, never rank-flips backends). (FR-16/FR-20 also touched: canonical-mix weighting + frontend report columns.)
- **OQs:** OQ-6 SUPERSEDED → container substrate; OQ-7 re-scoped to RESOLVED (netns per-service) + kind deferred; OQ-4 REVISED (two adapters + frontend promoted to bonus). **Decisions kept intact:** single-model fleet (OQ-1), layered scoring (OQ-2), manual finalists/advisory (FR-21/NR-1/NR-7), Java/ad + kind deferred. NR-2 revised (frontend bonus now in scope).
- **Consistency note:** reconciled to PLAN.md v0.3 (M0=`build_service_image`/FR-7b, M1=compose fleet/FR-7c, M2=journey+Adapter B/FR-9/9a, M3=layered scoring/FR-13/14/16, M4=frontend bonus lane/FR-23+9b, M5=bonus scoring/FR-24, M6=finalists+report/FR-20/21).
