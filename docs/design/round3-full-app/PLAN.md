# Round 3 — Full 9-Service Application Round — Implementation Plan

**Version:** 0.3 (CONSOLIDATED — sequences the full Round-3 design corpus into one authoritative build roadmap)
**Date:** 2026-06-24
**Status:** Plan — DESIGN/SEQUENCING ONLY, no code. Consolidates the 8-doc corpus and supersedes the v0.2 netns-fleet framing. The hard design thinking is done across the corpus; this plan turns it into clean milestone execution.
**Paired with:** REQUIREMENTS.md v0.2 (the FRs are stable; v0.3 here only re-substrates the fleet and adds the frontend-bonus + layered-scoring milestones the post-v0.2 corpus designed).

---

## §0 — What v0.3 consolidates + supersedes (traceable supersession)

v0.3 is a **consolidation pass**: the 8 Round-3 design docs each settled one slice of the build; this plan
sequences all of them into M0..Mn so the build is execution, not re-decision. The single load-bearing
**supersession** v0.3 records:

> **SUPERSEDED — the v0.2 "verdict B / no-Docker / Seatbelt shared-loopback fleet" framing.**
> CONTAINMENT_SPIKE.md §0 (VERIFIED CORRECTION, 2026-06-24) overturned verdict B for the fleet:
> OB services dial each other over **gRPC**, and under the macOS Seatbelt loopback profile **sandboxed
> gRPC dial-out is DENIED** — and the only Seatbelt rule that lets gRPC dial (`remote ip "*"`) re-opens
> full external egress. **There is no Seatbelt profile that permits sandboxed gRPC loopback dial-out
> while denying egress.** Therefore:
> - **The FLEET runs on a CONTAINER substrate (docker-compose first, kind later)**, NOT a netns/Seatbelt
>   process fleet. Compose `internal: true` gives gRPC-over-service-DNS + network-layer egress-deny
>   simultaneously (COMPOSE_FLEET_PROTOTYPE.md, LIVE-VALIDATED on macOS Docker).
> - **netns is RETAINED but re-scoped:** it is the Linux substrate for **per-service SANDBOXED dial-out
>   scoring** (checkout's 6 stubs, recommendation's 1 stub — Round 2's latent macOS gap), NOT the fleet.
>   netns_substrate.py is LIVE-VALIDATED on Linux (real gRPC channel ready + egress denied).
> - The v0.2 PLAN's "M2 = N-server Seatbelt fleet generalization of `_run_checkout_cell`" is **replaced**
>   by M0–M1 (per-language image build + compose-fleet generator). REQUIREMENTS FR-7a's macOS-shared-
>   loopback weakening now applies only to the **non-sandboxed dial-out fallback on macOS**, not the fleet
>   (the container fleet has network-layer containment, no shared host loopback plane).

**Platform split to carry through every milestone (do not re-litigate):**

| Surface | macOS dev host | Linux CI |
|---|---|---|
| **Fleet** (all 9 + journey) | **docker-compose, `internal` egress-deny** — works natively (validated) | docker-compose or **kind** (max fidelity) |
| **Per-service sandboxed dial-out scoring** (checkout/recommendation) | DEGRADES (Seatbelt can't; non-sandboxed fallback under FR-7a posture) | **netns** `unshare -rn` shared-netns (validated) |
| **Per-service leaf (inbound) scoring** (catalog/cart/currency/…) | Seatbelt sandbox works (verdict B still holds for inbound) | Seatbelt or netns |

**Decisions LOCKED across the corpus (carried, not re-opened):** single-model fleet (OQ-1); layered
scoring = per-step coverage headline + per-service fault attribution + derived "journey completed"
boolean (OQ-2); container substrate for the fleet (compose first / kind later); frontend = BONUS with
canonical substitution (never zeroes a model); journey adapter B (direct-gRPC) is the always-on
diagnostic backbone, adapter A (HTTP) the canonical journey; Java/adservice deferred to v2 (leaf, off
the journey, non-critical); reuse-not-regenerate workdirs (Mottainai, OQ-3); no auto-tournament
orchestrator (manual finalists, advisory report FR-21/NR-7).

---

## What's-already-done ledger (the plan starts from THIS reality)

| Asset | State | Where |
|---|---|---|
| 5 per-service behavioral suites + reference fixtures | **SHIPPED** | `behavioral/{catalog,email,cart,recommendation,checkout}_suite.py` (+ currency/charge/shipping/ad/pricing) |
| Startup contracts + launchers | **SHIPPED** (`resolve_serve_command`, `StartupContract`, `_DEFAULTS` for 4 langs; Java absent) | `behavioral/contract.py` |
| Offline provisioning (Go stubs / .pydeps / dotnet publish / node closure) | **SHIPPED** (Java = none) | `behavioral/provision.py`, `node_runtime/`, `setup_go_stubs`, `publish_dotnet_service` |
| Dependency stub harnesses + ground-truth oracle | **SHIPPED** | `checkout_stubs.py`, `recommendation_stubs.py`, `charge_suite.py` |
| **Compose-fleet substrate** | **PROTOTYPE, LIVE-VALIDATED on macOS Docker** (2-svc rec→catalog, coverage 1.0, egress denied, clean teardown) | `compose-prototype/`, `tests/integration/test_compose_fleet_prototype.py` |
| **netns substrate** (per-service Linux sandboxed dial-out) | **PROTOTYPE, LIVE-VALIDATED on Linux** (real gRPC + egress-deny, coverage 1.0) | `netns_substrate.py`, `tests/integration/test_netns_substrate_smoke.py` |
| Containerization scoped (5 lanes, build_service_image, canonical Dockerfiles, effort) | **SCOPED** (no code) | `CONTAINERIZATION_SCOPING.md` |
| Journey + 2 adapters + frontend-bonus model designed | **DESIGNED** (no code) | `JOURNEY_DESIGN.md`, `FRONTEND_OPENAPI_CONTRACT.md`, `FRONTEND_LANE_SCOPING.md` |
| Scorecard / runner / aggregate (lanes D2–D5, median/IQR/leaderboard, persistence) | **SHIPPED** | `scorecard.py`, `runner.py`, `aggregate.py` |

So: **the two substrates are validated, the suites/contracts/provisioning exist, the journey+frontend are
designed.** The remaining build is (1) the per-language image builder, (2) the N-service fleet generator,
(3) the journey driver + layered scorer, (4) the frontend bonus lane.

---

## Sequenced milestone plan (M0..M6 + deferred)

> Critical-path prerequisite (inherited, still real): the **Track-2 startup contracts** for
> cart/catalog/recommendation/email must exist (only checkout's was complete at v0.2). The fleet/image
> CMD derives from `contract.py` `resolve_serve_command`; if a contract is missing, add it (scope to budget).

### M0 — `build_service_image` + per-language Dockerfile templates
- **Goal:** deterministically build one container image per generated service, offline, reusing existing provisioning.
- **Scope:** a `benchmark_matrix.containers` layer: 5 parameterized Dockerfile templates (Go/Python/Node first — the ~80% reuse lanes — then **C# warm-NuGet bake**); `build_service_image(service, workdir)` stages generated source + offline deps + OB gRPC stubs (relocates `setup_go_stubs` / `.pydeps` / node closure / `publish_dotnet_service` into a build stage). Mirror the digest-pinned, multi-arch microservices-demo-latest Dockerfiles (CONTAINERIZATION_SCOPING §7b).
- **Dependencies:** none upstream (provisioning exists). Unblocks M1.
- **Reuse vs net-new:** REUSE = all 4 non-Java offline closures + run CMDs (`contract._DEFAULTS`); the compose prototype's `prepare_build_context.sh` is the existence-proof of the staging. NET-NEW = the 5 templates + builder + offline base-image prep/cache store + C# warm-NuGet snapshot.
- **Exit criteria (macOS-runnable):** `build_service_image` produces a runnable image for Go + Python + Node + C# services from a generated workdir; each boots and answers one RPC in a one-container smoke (extend `compose-prototype` patterns). Stretch: build succeeds under `--network=none` after base-image+cache pre-pull (offline hermeticity).
- **Risk/OQ:** OQ-C1 (offline base availability), OQ-C2 (build-time scale / layer caching), OQ-C4 (arm64 vs amd64 dep caches), OQ-C6 (C# cold-NuGet — the one load-bearing unsolved reuse gap).
- **Effort:** **~1 suite** (Go/Python/Node thin wrappers ≈ one suite total; **+~¼ suite** C# warm-NuGet bake).

### M1 — full N-service compose-fleet generator
- **Goal:** stand up a finalist's full 9-backend fleet together, egress-denied, peers wired by service-DNS.
- **Scope:** generalize the validated 2-service `compose-prototype` to all 8 (v1) / 9 backends: emit a docker-compose with one container per service on an `internal: true` `fleet` network (network-layer egress-deny); inject every `*_SERVICE_ADDR` dep edge as `SERVICE: name:port` from the startup contracts; dependency-ordered readiness wiring; **encode the two faithfulness traps** — emailservice `(listen 8080 / dial 5000)` port asymmetry and the **redis-cart** infra sidecar for cartservice (JOURNEY_DESIGN §3); guaranteed `compose down -v --remove-orphans` teardown on every path.
- **Dependencies:** M0 (images). Unblocks M2.
- **Reuse vs net-new:** REUSE = the validated compose prototype topology (`internal` net, service-DNS, `DIAL`-log call-counter, finally-teardown); the `*_SERVICE_ADDR` convention from `contract.py`. NET-NEW = the N-service compose generator + redis sidecar + email port-remap + dep-ordered bring-up at N.
- **Exit criteria (macOS-runnable):** an SDK-reference 8-service fleet boots on macOS Docker, all services become ready, every declared `*_SERVICE_ADDR` resolves over service-DNS, and egress to `1.1.1.1:443` is DENIED from a pure-backend container; teardown leaves zero containers/networks.
- **Risk/OQ:** OQ-C7 (compose vs kind parity — keep `*_SERVICE_ADDR` substrate-parameterized), redis/email faithfulness, FR-7a (now satisfied by network-layer containment, not shared loopback).
- **Effort:** **~1 suite** (fleet-compose generation + egress-deny + dep wiring, shared across languages).

### M2 — transport-agnostic journey + Adapter B (direct-gRPC, always-on)
- **Goal:** the layered backend journey scored over the live fleet, contestant-pure.
- **Scope:** define the journey ONCE (the 5 logical steps browse→setCurrency→addToCart→viewCart→checkout, JOURNEY_DESIGN §2.1) with transport-independent expected outcomes + SDK ground-truth oracle (promote `checkout_stubs.GroundTruth` math to a fleet oracle over the seeded catalog/cart fixtures); build **Adapter B** — an SDK-authored direct-gRPC driver replaying the §1 fan-out against the live fleet, reusing the validated checkout-suite 6-dep PlaceOrder path but against **live contestant backends** instead of stubs. Always-run diagnostic backbone.
- **Dependencies:** M1 (live fleet). Unblocks M3.
- **Reuse vs net-new:** REUSE = the `checkout_suite`/`*_suite` gRPC client machinery; `checkout_stubs.GroundTruth` oracle math; the 9-SKU/currency/future-dated-payload fixtures (JOURNEY_DESIGN §1). NET-NEW = the transport-agnostic journey spec, the fleet-level oracle, the Adapter-B driver.
- **Exit criteria (macOS-runnable):** Adapter B run against a **full SDK-reference 9-service mesh** scores **100% step coverage** (the R2-S3 "prove the journey on a known-good mesh before scoring any model" discipline); a deliberately-broken upstream (break payment) makes only checkout's step fail.
- **Risk/OQ:** mesh-compatibility of reused workdirs (OQ-3 — verify non-checkout services honor `*_SERVICE_ADDR` at runtime); oracle correctness.
- **Effort:** **~1 suite** (journey spec + oracle + driver).

### M3 — layered scoring → scorecard (backend)
- **Goal:** turn journey results into the layered system score with honest per-service attribution.
- **Scope:** `score.py` — **per-step coverage** (headline, weighted by the canonical locust mix browse 10…checkout 1 and/or unweighted, JOURNEY_DESIGN §4.1) + **per-service fault attribution** via the `*_SERVICE_ADDR` call-counter (`scorecard.py RPC_RESULT_TO_ADDR`) classifying each failed step as `model-fault:S` / `propagated:S←D` / `degraded:S` / `harness` (FR-14) + derived **"canonical journey completed" boolean** (FR-13). Fold into the scorecard D2–D5 lane sections alongside (not replacing) Round-1/2 per-service leaderboard columns; surface "deepest journey step reached" (FR-21).
- **Dependencies:** M2 (journey results). Unblocks M4-scoring + M5.
- **Reuse vs net-new:** REUSE = `BehavioralResult` model-fault-vs-degrade discipline; `aggregate._median/_iqr`; leaderboard + durable persistence + verbatim-id join; `scorecard.py` markdown patterns. NET-NEW = step-coverage + cross-mesh attribution scorer + system-report surfacing.
- **Exit criteria:** run on the SDK-reference mesh + 2 deliberately-broken meshes (break payment; break catalog) → each fault attributed to the **right service** with the **right class**; a downstream service is never charged `model-fault` for an upstream break; an all-degrade run is flagged low-confidence (FR-22).
- **Risk/OQ:** attribution correctness across the 6-deep checkout fan-out (the known-broken-mesh tests are the gate).
- **Effort:** **~1 suite** (layered scorer + attribution).

### M4 — frontend BONUS lane (seed + gate + substitution + Adapter A)
- **Goal:** add the 10th, BONUS frontend service that can never zero a model.
- **Scope:** the `frontend` seed (Go lane reuse) + HTTP-readiness `StartupContract` variant; the journey-facing HTTP contract suite (FRONTEND_OPENAPI_CONTRACT §1–§3) as an executable spec; the **health+OpenAPI gate** (boot → route presence → **stateful end-to-end checkout against a known-good backend fleet** → advisory orchestration sanity); the **canonical-substitution** mechanism (gate FAIL → mount upstream `src/frontend`, wired via `*_SERVICE_ADDR`, clean fail-to-canonical, no partial mount); **Adapter A** — the form-encoded HTTP locust-mix driver that runs unchanged over either frontend (the contract is the seam).
- **Dependencies:** M1 (fleet for backends) + M2 (journey definition). Independent of M3.
- **Reuse vs net-new:** REUSE = Go container lane + `setup_go_stubs` (frontend is "just another Go service"); the canonical `src/frontend` as the fallback image (build once); `*_SERVICE_ADDR` dep-binding + egress-denied net. NET-NEW = the frontend seed, the HTTP contract suite, the gate, the substitution switch + `frontend=generated|canonical-substituted` run-report field, the HTTP-readiness contract mode, Adapter A.
- **Exit criteria (macOS-runnable):** a **subtly-broken** generated frontend (renders a confirmation page **without a real order id**) **FAILS the gate and falls to canonical cleanly**; Adapter A then completes the full HTTP journey over the canonical frontend; the run report records which frontend ran + gate verdict + reason (OQ-J4). A correct generated frontend PASSES and Adapter A is green over it.
- **Risk/OQ:** **R2/OQ-J1 gate robustness (load-bearing — lean strict)**; R3 clean fail-to-canonical; R4 ad-deferred graceful-degrade (ads non-critical); R5/OQ-J2 double-attribution (Adapter B is the disambiguator).
- **Effort:** **~1 suite** (most of it the contract suite + gate + substitution wiring; lane + fallback image are reuse).

### M5 — frontend bonus → scorecard (additive, capped)
- **Goal:** reward the frontend as pure upside without distorting the backend ranking.
- **Scope:** the frontend bonus scorer — (a) frontend service score (route correctness + §3 orchestration fidelity, gate-gated, 0 if absent/failed) + (b) `journey_via_generated_frontend` flag; fold as **separate columns** (`backend_score` ranked, `frontend_bonus` additive tie-break/annotation); the substituted-run `canonical_journey_completed` authenticity flag (NOT frontend bonus); the bonus **cap** so it stays a tie-break, never a rank-flipper.
- **Dependencies:** M3 (backend scorecard) + M4 (frontend gate results).
- **Reuse vs net-new:** REUSE = scorecard column/leaderboard machinery. NET-NEW = bonus scorer + folding/cap.
- **Exit criteria:** a model with a brilliant frontend but weak backends **never outranks** a strong-backend model; bonus surfaces as a labeled "+frontend" tie-break; substituted runs show `frontend_bonus=0` + `canonical_journey_completed` set correctly.
- **Risk/OQ:** OQ-J3 (bonus magnitude/cap — must not dominate), OQ-F3 (don't tempt over-investment in frontend).
- **Effort:** **~¼ suite**.

### M6 — real finalists (single-model fleets) + system report + CLI + decision gate
- **Goal:** score the actual finalists end-to-end and decide if the round discriminates.
- **Scope:** each user-supplied finalist's **own** 9-service fleet (reuse workdirs by verbatim model id, regenerate only gaps — minimal/no new LLM spend, OQ-3); persist per-cell (Mottainai → $0 rescore); render `round3-system-report.{json,md}` + finalist leaderboard with cost/speed columns; `startd8 benchmark round3` CLI. **Advisory only** (FR-21), no auto-orchestrator.
- **Dependencies:** M3 + M5 (full scoring). Terminal milestone.
- **Reuse vs net-new:** REUSE = `deploy_harness.batch` verbatim-id join + `.model` sidecar; durable persistence; aggregate markdown rollup. NET-NEW = the report renderer + CLI + roster resolver (`roster.py`).
- **Exit criteria:** finalists ranked by system score with attribution + frontend-bonus columns; **decision gate** — does the journey discriminate finalists and is attribution trustworthy?
- **Effort:** **~½ suite** (report + CLI + roster; scoring already built).

### Deferred (post-v1)
- **kind/k8s substrate** (max fidelity; the canonical OB is k8s-native, no upstream compose — kind is where compose converges to canonical). NET-NEW: kind manifests + `NetworkPolicy` egress-deny; keep `*_SERVICE_ADDR` substrate-parameterized (OQ-C7).
- **Java/adservice** (leaf, off the canonical journey, non-critical; only lang with zero offline-build). Canonical-evidence lowered cost: `./gradlew downloadRepos` is a ready offline dep-prefetch hook + `installDist` is the build pattern → bake gradle cache + inject harness-owned `build.gradle` + add `_java_default` launcher (~½–¾ suite, not greenfield).
- **Offline `--network=none` build hermeticity** for Go/Python (pre-warm GOMODCACHE/wheels into build context; Node closure already vendored).
- **Linux CI for the per-service SANDBOXED dial-out scoring** (wire `netns_substrate.run_cell_in_shared_netns` into the checkout/recommendation cells — closes Round 2's latent macOS dial-out gap).
- **`edge`-network egress-deny hardening** (ingress frontend can still reach internet via `edge`; v2 egress-firewall sidecar).
- **Multi-arch amd64 CI images** + per-arch dep-cache baking (OQ-C4).

---

## Critical path + recommended first milestone

**Critical path:** Track-2 startup contracts (prereq) → **M0** (images) → **M1** (fleet) → **M2** (journey+Adapter B) → **M3** (layered scoring) → **M6** (finalists+report). M4→M5 (frontend bonus) is a **parallel branch** that joins at M5/M6 and is **never on the critical path** (it can never block backend scoring — that is the whole point of the substitution seam).

**Recommended first milestone: M0** (`build_service_image` + Go/Python/Node templates). It is the foundation everything else composes on, has the highest reuse (~80% existing closures), is fully macOS-runnable, and the compose prototype already proves the staging end-to-end for 2 of the lanes. Start the C# warm-NuGet bake in M0's back half (the one load-bearing unsolved reuse gap).

---

## Per-milestone effort read (in "suites")

| Milestone | Effort | Notes |
|---|---|---|
| M0 image builder | **~1 + ¼** | Go/Python/Node ≈ 1 suite total; C# warm-NuGet bake ≈ ¼ |
| M1 compose fleet | **~1** | generalize the validated 2-svc prototype to 8/9 |
| M2 journey + Adapter B | **~1** | journey spec + fleet oracle + direct-gRPC driver |
| M3 layered scoring | **~1** | step coverage + cross-mesh attribution |
| M4 frontend bonus lane | **~1** | mostly gate + substitution; lane/fallback = reuse |
| M5 frontend bonus → scorecard | **~¼** | bonus scorer + cap |
| M6 finalists + report + CLI | **~½** | scoring already built; reuse persistence/join |
| **v1 total** | **~5 suites** | Java + kind + offline-build hermeticity deferred |

Consistent with CONTAINERIZATION_SCOPING's "~1.5–2× a suite" for the container layer alone; the full
round (fleet + journey + layered scoring + frontend bonus) lands around **5 suites**, dominated by the
image builder, the fleet generator, and the layered scorer — most of it reuse-and-relocate.

---

## Consolidated OQ / risk register

| ID | Risk / open question | Milestone | Disposition |
|---|---|---|---|
| **Substrate split** | macOS Seatbelt can't host dial-out fleet; container fleet on macOS Docker, netns per-service dial-out needs Linux | all | **RESOLVED in §0** — container fleet (validated macOS) + netns per-service (validated Linux); carry the platform table |
| **Gate robustness** (R2/OQ-J1) | a subtly-broken generated frontend passes and pollutes Adapter-A signal | M4 | **load-bearing — lean strict**; stateful end-to-end checkout against known-good backends is the decisive defense |
| **Bonus cap** (OQ-J3/OQ-F3) | additive frontend bonus rank-flips backend ranking / tempts over-investment | M5 | cap low; rank on backend, bonus = tie-break only |
| **arm64 vs amd64** (OQ-C4) | dep caches (grpcio C-ext, NuGet, dotnet runtime-deps) are arch-specific | M0/deferred | build per-target-arch (upstream multi-arch default); Node closure is portable |
| **C# warm-NuGet bake** (OQ-C6) | `dotnet restore` is the only network step; cold cache breaks offline | M0 | the one unsolved reuse gap — bake+snapshot `~/.nuget`, then `--no-restore` publish |
| **Offline-build hermeticity** (OQ-C1/C2) | base images / dep caches must be pre-warmed or network silently re-opens; build scale ~9N | M0/deferred | pre-pull digest-pinned bases; cache model-invariant base+dep layers; fail closed |
| **email port-remap + redis** | email listens 8080 / dialed 5000; cartservice needs redis-cart | M1 | encode `(listen,dial)` pair per service; redis-cart = non-seed infra sidecar |
| **Attribution correctness** (FR-14) | mis-attributing an upstream break to a downstream service silently blames wrong model | M3 | known-broken-mesh tests (break payment/catalog) are the gate |
| **Mesh-compat of reused workdirs** (OQ-3) | Round-1/2 non-checkout services may not honor `*_SERVICE_ADDR` at runtime | M2 | verify at runtime; regenerate gaps (Mottainai saving partly evaporates if not) |
| **kind/compose parity** (OQ-C7) | egress-deny + service-DNS differ (compose `internal` vs k8s `NetworkPolicy`) | deferred | keep `*_SERVICE_ADDR` wiring substrate-parameterized so the driver is identical |
| **Track-2 contracts** (prereq) | fleet/image CMD needs startup contracts for all 9; only checkout's was complete | M0/M1 | add missing contracts (scope to budget) — the gating prerequisite |
| **Java deferred** (OQ-C5) | adservice off journey, only lang w/ zero offline build | deferred | v1 = 8 services; frontend `AD_SERVICE_ADDR` must degrade gracefully |

---

## Out of scope (this plan)
Auto-finalist-selection (NR-1/NR-7); load/perf/soak/chaos (NR-3); real external persistence beyond
journey-required fixtures (NR-5); best-of-breed as the default topology (single-model fleet only;
best-of-breed = optional diagnostic); the **deferred** set above (kind/k8s, Java/adservice, offline-build
hermeticity, Linux-CI per-service sandboxed dial-out, edge egress-deny, amd64 multi-arch).

---

**Footer (v0.2 → v0.3):** Reframed from a single FR→file plan into a **consolidated, sequenced
M0..M6 + deferred roadmap** spanning the full 8-doc corpus. **Recorded the load-bearing supersession**
(verdict B overturned → container fleet, netns re-scoped to per-service Linux dial-out). Added the
**container image-build milestone (M0)**, the **compose-fleet generator (M1)** replacing the v0.2 Seatbelt
N-server generalization, the **transport-agnostic journey + Adapter B (M2)**, **layered scoring (M3)**,
and the **frontend BONUS lane + bonus scoring (M4/M5)** the post-v0.2 corpus designed. Carried all LOCKED
decisions. Added a **what's-already-done ledger**, a **critical path + first milestone**, a **per-milestone
effort read (in suites)**, and a **consolidated OQ/risk register**. REQUIREMENTS FRs unchanged (v0.2
stable); v0.3 only re-substrates the fleet and adds the frontend/scoring milestones.
