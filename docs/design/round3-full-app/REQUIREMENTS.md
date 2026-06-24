# Round 3 — Full 9-Service Application Round — Requirements

**Version:** 0.2 (Post-planning + spike — self-reflective update)
**Date:** 2026-06-23
**Status:** Updated after the reflective-requirements planning pass and the containment spike. Open forks resolved; CRP next. No code yet.
**Owner SDK area:** `startd8.benchmark_matrix` (a new Round-3 "system" harness) + `startd8.deploy_harness` (reuse) + `startd8.benchmark_matrix.behavioral` (suite/stub/sandbox reuse) + seeds.
**Parents:**
- `docs/design/benchmark-scoring/FUNCTIONAL_CORRECTNESS_TRACK2_EXPANSION_REQUIREMENTS.md` (the per-service behavioral frontier; defines NR-X1 live full-mesh + NR-X2 generated-deps as **out of scope** there)
- `docs/design/local-deploy-harness/LOCAL_DEPLOY_HARNESS_REQUIREMENTS.md` (the shipped graded deploy ladder)
- `docs/design/model-benchmark/` (Summer 2026 benchmark; Rounds 1–2)
- `docs/design/round3-full-app/CONTAINMENT_SPIKE.md` (the M1 feasibility gate — **PASSED, verdict B**, folded into §0 + FR-7/7a)

---

## 0. Planning Insights (Self-Reflective Update)

The planning pass (reading the shipped `deploy_harness`, `behavioral` harness, and seeds) plus the **containment spike** (CONTAINMENT_SPIKE.md) resolved the two load-bearing forks and the security feasibility gate. Highlights:

| v0.1 assumption | Finding (planning + spike) | Impact |
|---|---|---|
| Build topology was an open fork (single-model vs best-of-breed vs hybrid). | Best-of-breed **recreates** the cross-model confound NR-X2 forbids (a great checkout scored badly because *another* model's payment is broken) — answers an ecosystem question no model tournament asks. | **OQ-1 RESOLVED → single-model fleet.** Each candidate builds all 9; its own fleet is deployed + scored as that model's system. Best-of-breed allowed only as an opt-in **diagnostic** view, never the headline. Topology FR (FR-15) now mandates single-model. |
| Scoring was an open fork (full-system pass/fail vs step credit vs per-service-in-integration). | Pure full-system pass/fail is **brutally lossy** — one weak service (e.g. email) zeros a finalist with 8 perfect services. | **OQ-2 RESOLVED → layered scoring.** Headline = per-journey-step coverage; PLUS per-service fault attribution; PLUS a derived boolean "canonical journey completed" flag. FR-13/14/16 updated. |
| Docker-per-service might be a hard prerequisite for co-running 9 untrusted servers. | Spike **verdict B (MEASURED):** macOS Seatbelt is per-process (no netns); N sandboxed servers co-exist, a sandboxed peer is reachable over loopback, external egress stays DENIED, teardown is clean. The existing sandbox **suffices** for a co-located fleet. | **Containment OQ RESOLVED → no Docker layer in v1.** Round 3 build does **not** grow by a Docker substrate; the new work is the N-server fleet orchestrator. M1 feasibility gate PASSED. |
| Multi-service isolation is "best-effort, recorded honestly" (vague). | Spike pinned the exact weakening: the fleet shares **one unrestricted 127.0.0.1 loopback plane** → a compromised/buggy service can reach **any** sibling or host loopback port, not just its declared deps. | **FR-7a now records this honestly + ACCEPTED** (all 9 are same-model output on a disposable host) with named mitigations + a concrete **escalation trigger → Docker (option C)**. |
| The shipped deploy harness is the Round-3 foundation. | **Only a partial foundation.** `deploy_app_local` is single-app/single-venv/single-port; `deploy_batch` deploys roots **independently and serially**, never together; `context_smoke` dials *pre-existing remote* producers, never *stands up* a fleet. | Deploy harness contributes **discovery + Python venv/install + readiness/health patterns**; the **co-deploy + inter-wiring is net-new** (the load-bearing FR-4/5/6 fleet orchestrator). |
| Isolation behaves the same everywhere. | Spike found the substrate is **platform-dependent**: on Linux CI the sandbox auto-selects `unshare -rn` (per-netns), which **removes** the FR-7a weakness but **breaks** shared-loopback peer reachability — so a Linux fleet needs a shared-netns / veth design. | v1 targets **macOS-style shared loopback**; a Linux fleet substrate is a **follow-up design** (NEW open question OQ-7 below), not resolved here. |

### Resolved open questions
- **OQ-1 (build topology) → SINGLE-MODEL FLEET.** Each candidate model builds all 9 services; its own fleet is deployed together and scored as that model's system. Best-of-breed REJECTED as the headline (recreates the NR-X2 cross-model confound); permitted only as an opt-in diagnostic view.
- **OQ-2 (scoring/attribution) → LAYERED.** Headline = per-journey-step coverage; PLUS per-service fault attribution; PLUS a derived boolean "canonical journey completed" flag. Pure full-system pass/fail REJECTED as the sole metric.
- **OQ-6 (multi-service containment) → VERDICT B (no Docker in v1).** The existing Seatbelt sandbox co-runs the fleet; the shared-loopback weakening is recorded + accepted (FR-7a) with a Docker escalation trigger. M1 feasibility gate PASSED (CONTAINMENT_SPIKE.md).

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
- Kernel-level isolation beyond the inherited best-effort host controls (parent NR-T2-2). The spike confirmed the existing Seatbelt sandbox suffices for the co-located fleet (verdict B, no Docker in v1); the multi-service weakening is recorded + accepted in FR-7a with a Docker escalation trigger.
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
- **FR-7** Each service runs under the **same untrusted-code controls** as a single SUT (scrubbed env, rlimits, loopback-allowed/egress-denied). **Spike-confirmed (verdict B):** the existing Seatbelt sandbox co-runs N such servers — measured co-existence, loopback peer reachability, sustained external-egress denial, and clean process-group teardown — so **no Docker layer is required in v1**.
- **FR-7a** (containment weakening — recorded + ACCEPTED). On macOS (Seatbelt, no netns) the N co-located untrusted services share **one unrestricted 127.0.0.1 loopback plane**: the sandbox guarantees external-egress denial, per-process rlimits, and process-group teardown, but does **NOT** restrict *which* loopback port a service may dial. Therefore a compromised/buggy service can reach **any sibling OR any host-side loopback service**, not only its wired dependencies. This is captured in provenance, not hidden. **ACCEPTED** because all 9 services are same-model output on a disposable host and external exfiltration stays blocked. **Mitigations (required):** (i) bind the fleet on free, **randomized** ports not revealed to services beyond their declared deps; (ii) ensure **no sensitive host service** (real DB, secret-holding daemon) listens on `127.0.0.1` during a run; (iii) keep secrets out via existing `scrub_env`. **Escalation trigger → Docker (option C):** mixing services from **different models/tenants** in one fleet, or running on a **non-disposable host with co-located sensitive services** — either makes the shared loopback plane a cross-tenant breach surface and forces per-netns (`unshare -rn` on Linux) or Docker-per-service. See CONTAINMENT_SPIKE.md §4 and OQ-7 for the Linux substrate caveat.
- **FR-8** The fleet deployer is **polyglot**: it must launch C# (cart), Go (catalog/checkout/shipping), Node (currency/payment), Java (ad), Python (recommendation/email) servers via the existing `resolve_serve_command` hooks, degrading honestly per service where a toolchain is genuinely absent (FR-32 inheritance).

### Cross-service journeys & ground truth
- **FR-9** Define a fixed set of **cross-service user journeys** as SDK-authored gRPC client sequences against the live mesh, at minimum the canonical: **browse** (productcatalog ListProducts/GetProduct) → **currency** (Convert) → **add-to-cart** (cart AddItem→GetCart) → **shipping quote** → **checkout PlaceOrder** (which internally fans out to payment + email) → **confirmation** (assert PlaceOrderResponse + that payment/email were dialed).
- **FR-10** Each journey carries **SDK ground truth** (the oracle): the expected order total = Σ(price×qty) currency-converted + shipping, non-empty tracking_id/transaction_id, cart emptied post-order, etc. — promote the `CheckoutStubHarness.GroundTruth` oracle math to a **fleet-level oracle** that knows the seeded catalog/cart fixtures.
- **FR-11** Journeys must be defined as an **ordered list of steps**, each step attributable to the **service that owns it** (browse→catalog, convert→currency, …), so a step failure names a responsible service (feeds attribution, OQ-2).
- **FR-12** State the **catalog/cart fixtures** the journey assumes (reuse the Track-2 expansion `products.json` state-fixture mechanism); the journey cannot assert against an unknown catalog.

### Scoring & attribution (depends on OQ-2)
- **FR-13** Produce, per finalist, a **layered system result** (OQ-2 RESOLVED), NOT a single pass/fail. Three layers: **(headline) per-journey-step coverage** — fraction of journey steps that passed, so partial credit survives one broken service; **(attribution) per-service fault attribution** — which service caused each failed/degraded step (FR-14); **(derived) a boolean "canonical journey completed" flag** — did the full browse→checkout→confirm journey complete end-to-end. The boolean is reported but is **not** the sole/headline number (pure full-system pass/fail REJECTED — one weak service would zero a finalist with 8 perfect services).
- **FR-14** **Attribution honesty (the core requirement):** every failed/degraded step records the **owning service** and a **fault class**: `model-fault:S` (S's own service produced a wrong/missing result), `propagated:S←D` (S behaved correctly given a broken upstream D), `degraded:S` (S unrunnable — missing/won't-boot/toolchain), or `harness`. A downstream service must **not** be charged a model-fault for a fault originating upstream (mirror the per-service `model_fault` vs `degrade` discipline; generalize across the mesh).
- **FR-15** **Topology = single-model fleet (OQ-1 RESOLVED); no cross-model dependency mixing in the headline result.** Each candidate model builds all 9 services; its **own** fleet is deployed together and scored as that model's system. Every service in a finalist's mesh is **that same finalist's** build, so a journey score is attributable to one model — this is how Round 3 *honors* the spirit of NR-X2 while crossing the frontier (the confound is *within one model*, not *across models*). Best-of-breed (mixing each model's best per-service build) is **REJECTED as the headline** — it recreates the exact cross-model confound NR-X2 forbids — and is permitted **only as an opt-in DIAGNOSTIC view** (to localize whether a finalist's journey failure is its own checkout vs its own dependency), explicitly labeled non-attributable-to-one-model, with FR-14's `propagated` class mandatory in that mode.
- **FR-16** Roll up step coverage to a **journey pass-rate** and a **system score** per finalist (the headline layer), and surface the derived **"canonical journey completed" boolean** alongside it; both surface alongside (not replacing) the Round-1/2 per-service leaderboard columns.

### Reuse of shipped infra
- **FR-17** Reuse `deploy_harness` discovery (entrypoint/deps/mode detection) and venv/install for the **Python** services; reuse `run_service_sandboxed` for the launch+readiness+teardown of **every** service. Do **not** rebuild install/boot/health.
- **FR-18** Reuse the `*_SERVICE_ADDR` env convention and `demo.proto`-derived dependency edges already encoded in the checkout seed `startup.dependency_addr_env`.
- **FR-19** Reuse durable per-cell persistence (R3-S1) and the join-by-verbatim-model-id sidecar (`deploy_harness.batch`) so a Round-3 system run is **persist-then-rescore** (Mottainai) — re-score a captured fleet for $0 as journeys/oracles improve.

### Scorecard surfacing
- **FR-20** Emit a Round-3 **system report** (`round3-system-report.{json,md}`): per finalist, per journey, per step — status + fault class + owning service; a fleet bring-up roll-up (which services booted/were-ready); and a finalist leaderboard by system score with cost/speed columns (reuse aggregate.py patterns).
- **FR-21** The report must make the **integration frontier visible**: for each finalist, "deepest journey step reached" (analogous to `highest_stage`), so a finalist that builds 9 services that boot but never complete checkout is distinguishable from one that completes the full journey.

### Degrade honesty (cross-cutting)
- **FR-22** Any environment/toolchain/missing-service condition degrades **the specific affected steps** with a typed reason and is counted as `degraded`, never as a model-fault and never as a silent 0 (inherits FR-32). A run where **most** steps degrade must be flagged as low-confidence (no all-degrade masquerading as a system pass/fail).

---

## 4. Non-Requirements

- **NR-1** No auto-selection of finalists (manual; NR-7).
- **NR-2** No real frontend/browser; no generated loadgenerator (journey driver is SDK-authored).
- **NR-3** No load/perf/soak/chaos.
- **NR-4** No kernel isolation beyond inherited best-effort host controls (and Round 3 *weakens* the single-SUT story — recorded, FR-7a).
- **NR-5** No real external persistence backends unless a journey needs provisioned state (reuse fixtures).
- **NR-6** Round 3 does **not** re-implement per-service scoring; it composes services and scores the *system*.
- **NR-7** (inherited) No cross-model dependency mixing as the default — see FR-15/OQ-1.

---

## 5. Open Questions

> **Status after planning + spike:** OQ-1, OQ-2, OQ-6 are **RESOLVED** (see §0). They are retained below for the decision record. OQ-3/4/5 remain planning-resolvable. **OQ-7 (NEW)** — the Linux fleet isolation substrate — is **left open**.

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

### OQ-4 — The journey driver: SDK-authored client vs generated frontend
- **Recommendation: SDK-authored gRPC journey client (reuse the `checkout_suite` client pattern).** No OB `frontend`/`loadgenerator` seed exists, and a generated frontend would itself be a 10th scored service confounding the journey. The SDK owns the journey + oracle (it must, to be ground truth). Defer a generated-frontend variant.

### OQ-5 — Email/side-effect & ad/recommendation steps in the journey
email returns `Empty` (no observable) and ad/recommendation aren't on the purchase path. Include them as journey steps?
- **Recommendation: keep email as a *call-counter* step inside checkout (reuse FR-CO-8 counter observable), and treat ad/recommendation as **optional browse-adjacent** steps that degrade-only (FR-3a) rather than gating the purchase journey.** Resolve final inclusion in planning against discrimination value.

### OQ-6 — Multi-service isolation containment (security) — **RESOLVED → verdict B, no Docker in v1** (CONTAINMENT_SPIKE.md; see §0, FR-7/7a)
Running 9 untrusted servers concurrently on one loopback plane weakens the single-SUT seatbelt story. Is best-effort host control + recorded honesty sufficient, or is Docker/netns-per-service a hard prerequisite?
- **RESOLVED by the containment spike (M1 feasibility gate, PASSED).** MEASURED on macOS: N sandboxed servers co-exist, a sandboxed peer is reachable over loopback, external egress stays DENIED, and teardown is clean — so the existing sandbox **suffices** and **no Docker layer is needed in v1**. The shared-unrestricted-loopback weakening is recorded + accepted in **FR-7a** with named mitigations and a concrete Docker escalation trigger (different models/tenants in one fleet, or a non-disposable host with sensitive co-located services).

### OQ-7 — (NEW, OPEN) Linux fleet isolation substrate
The isolation substrate is **platform-dependent**. v1 targets the **macOS Seatbelt shared-loopback** plane (FR-7a). On Linux CI the sandbox auto-selects `unshare -rn` (per-netns), which **removes** the FR-7a weakness but **breaks** shared-loopback peer reachability — peers in separate netns cannot dial each other's `127.0.0.1`, so the dependency wiring Round 3 depends on would not work.
- **Open (deferred to a follow-up design).** A Linux fleet needs a **shared-netns / veth-bridge design** — e.g. run all 9 services inside ONE shared network namespace (restoring peer reachability) while keeping external-egress denial. v1 does **not** target Linux; this is flagged as the substrate's platform gap, not resolved here.

---

*v0.2 — post-planning + containment spike. The two forks (OQ-1 topology → single-model fleet, OQ-2 scoring → layered) and the containment gate (OQ-6 → verdict B) are now resolved; the load-bearing build is the N-server fleet orchestrator. NEW OQ-7 (Linux substrate) left open.*

---

**Footer (v0.1 → v0.2 delta):** 3 open forks **resolved** (OQ-1 topology → single-model fleet; OQ-2 scoring → layered; OQ-6 containment → spike verdict B, no Docker v1); 5 FRs **narrowed/updated in place** (FR-2 topology, FR-7 + new FR-7a isolation, FR-13 layered scoring, FR-15 single-model headline, FR-16 derived-boolean surfacing); 1 FR **added** (FR-7a split out as its own recorded-weakening requirement); 1 open question **added** (OQ-7 Linux substrate). No FRs superseded/removed.
