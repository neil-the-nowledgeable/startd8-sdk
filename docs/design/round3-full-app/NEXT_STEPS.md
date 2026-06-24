# Round 3 — NEXT_STEPS (cold-start runbook)

**Date:** 2026-06-24 · **Reads from:** PLAN.md v0.3 + REQUIREMENTS.md v0.3 (do not re-derive — this is a pointer/runbook)

---

## Status

Round 3 (full 9-service Online Boutique system round) is **design + plan complete** (PLAN v0.3, REQUIREMENTS v0.3 reconciled). No Round-3 build code yet; the substrates and per-service assets it composes on are shipped/validated.

**Already SHIPPED / VALIDATED (start from this reality, don't rebuild):**
- **5 per-service behavioral suites + reference fixtures** — `behavioral/{catalog,email,cart,recommendation,checkout}_suite.py` (+ currency/charge/shipping/ad/pricing).
- **Startup contracts + launchers** — `resolve_serve_command`, `StartupContract`, `_DEFAULTS` for 4 langs (Java absent) — `behavioral/contract.py`.
- **Offline provisioning** — Go stubs / `.pydeps` / `dotnet publish` / node closure (`behavioral/provision.py`, `node_runtime/`).
- **Compose-fleet substrate** — PROTOTYPE, **LIVE-VALIDATED on macOS Docker** (2-svc rec→catalog, coverage 1.0, egress denied, clean teardown) — `compose-prototype/`, `tests/integration/test_compose_fleet_prototype.py`.
- **netns substrate** — PROTOTYPE, **LIVE-VALIDATED on Linux** (real gRPC + egress-deny) — `netns_substrate.py`, `tests/integration/test_netns_substrate_smoke.py`.
- **Containerization SCOPED** (5 lanes, `build_service_image`, Dockerfile patterns) and **journey + frontend DESIGNED** (no code).
- **Scorecard / runner / aggregate** — `scorecard.py`, `runner.py`, `aggregate.py`.

---

## Start here → M0 (`build_service_image` + Go/Python/Node Dockerfile templates)

**Why M0 first:** foundation everything composes on, highest reuse (~80% existing offline closures), fully **macOS-runnable**, and the compose prototype already proves the staging end-to-end for 2 lanes.

**Concrete first actions:**
1. Add a `benchmark_matrix.containers` layer with `build_service_image(service, workdir)`.
2. Write the **Go / Python / Node** parameterized Dockerfile templates (thin wrappers ≈ 1 suite total): stage generated source + offline deps + OB gRPC stubs into a build stage; derive `CMD` from `contract.resolve_serve_command`. Seed from `compose-prototype/` Dockerfiles + `prepare_build_context.sh`.
3. In M0's back half, start the **C# warm-NuGet bake** (`+¼` suite — the one load-bearing offline gap: bake+snapshot `~/.nuget`, then `--no-restore` publish).

**Prereq (don't skip):** the **Track-2 startup contracts** for cart/catalog/recommendation/email must exist (only checkout's was complete). The image/fleet CMD derives from `contract.resolve_serve_command`; add any missing contract (scope to budget).

**Exit criterion (M0):** `build_service_image` produces a runnable image for Go + Python + Node + C# from a generated workdir; each boots and answers one RPC in a one-container smoke (extend compose-prototype patterns). *Stretch:* build under `--network=none` after base+cache pre-pull (offline hermeticity).

---

## Critical path

```
Track-2 contracts (DONE/scope gaps) → M0 → M1 → M2 → M3 → M6
                                                    └ M4 → M5  (frontend BONUS — PARALLEL branch, joins at M5/M6, NEVER on the critical path)
```
The frontend bonus branch can never block backend scoring — that is the whole point of the substitution seam.

---

## Per-milestone one-liners (goal · exit · effort — from PLAN v0.3)

| M | Goal | Exit criterion | Effort |
|---|---|---|---|
| **M0** | `build_service_image` + Go/Python/Node Dockerfiles (+C# warm-NuGet) | runnable image per lang from a workdir; boots + 1 RPC in a 1-container smoke | ~1 + ¼ |
| **M1** | N-service compose-fleet generator (8/9 backends, egress-denied, service-DNS) | SDK-ref 8-svc fleet boots on macOS Docker; every `*_SERVICE_ADDR` resolves; egress to 1.1.1.1:443 DENIED; teardown leaves zero containers | ~1 |
| **M2** | Transport-agnostic journey + Adapter B (direct-gRPC, always-on) | Adapter B over a known-good 9-svc mesh = 100% step coverage; break payment → only checkout's step fails | ~1 |
| **M3** | Layered scoring → scorecard (per-step coverage + per-service fault attribution + journey-completed bool) | run on SDK-ref + 2 broken meshes (break payment / catalog) → each fault attributed to right service+class; downstream never charged model-fault for upstream break; all-degrade flagged low-confidence | ~1 |
| **M4** | Frontend BONUS lane (seed + health/OpenAPI gate + canonical substitution + Adapter A) | a subtly-broken frontend (confirmation w/o real order id) FAILS gate + falls to canonical cleanly; Adapter A green over canonical; report records which ran + verdict | ~1 |
| **M5** | Frontend bonus → scorecard (additive, capped) | brilliant-frontend/weak-backend model never outranks strong-backend; bonus = labeled "+frontend" tie-break; substituted runs show `frontend_bonus=0` | ~¼ |
| **M6** | Real finalists (single-model fleets) + system report + CLI + decision gate | finalists ranked by system score + attribution + frontend-bonus columns; decision gate: does the journey discriminate + is attribution trustworthy? | ~½ |

**v1 total ≈ 5 suites** (Java + kind + offline-build hermeticity deferred).

---

## Deferred set (+ pick-up trigger)

| Deferred | Trigger to pick up |
|---|---|
| **kind/k8s fleet substrate** (max fidelity; canonical OB is k8s-native, no upstream compose) | need cross-host CI fidelity / NetworkPolicy egress-deny beyond compose `internal` |
| **Java / adservice** (leaf, off journey; only lang w/ zero offline build) | a journey needs ad, or budget for the `./gradlew downloadRepos` + gradle-cache bake (~½–¾ suite) |
| **Offline `--network=none` build hermeticity** (Go/Python) | air-gapped CI / reproducibility requirement (pre-warm GOMODCACHE/wheels into build context) |
| **Linux CI per-service SANDBOXED dial-out** (wire `netns_substrate.run_cell_in_shared_netns` into checkout/recommendation cells) | closing Round-2's latent macOS dial-out gap on a Linux runner |
| **amd64 multi-arch images** + per-arch dep-cache bake | CI runs on amd64 (arm64 dep caches are arch-specific: grpcio C-ext, NuGet, dotnet runtime-deps) |
| **`edge`-network egress-deny hardening** | ingress frontend reaching the internet via `edge` becomes a concern (v2 egress-firewall sidecar) |

---

## Open decisions / risks to watch

- **Frontend gate robustness (R2/OQ-J1 — load-bearing):** lean strict. The **stateful end-to-end checkout against known-good backends** is the decisive defense against a subtly-broken frontend (confirmation page w/o a real order id).
- **Bonus cap (OQ-J3/OQ-F3):** cap low — rank on `backend_score`, frontend is tie-break ONLY; must never rank-flip; don't tempt over-investment in the frontend.
- **C# warm-NuGet bake (OQ-C6):** the one unsolved reuse gap — `dotnet restore` is the only network step; cold cache breaks offline. Bake+snapshot `~/.nuget`, then `--no-restore` publish.
- **arm64 vs amd64 (OQ-C4):** dep caches are arch-specific; build per-target-arch (Node closure is portable).
- **Faithfulness traps (M1):** emailservice **port asymmetry** (`listen 8080 / dial 5000`) and the **redis-cart** infra sidecar cartservice needs — encode the `(listen,dial)` pair per service + redis as a non-seed infra sidecar.
- **Mesh-compat of reused workdirs (OQ-3):** verify Round-1/2 non-checkout services honor `*_SERVICE_ADDR` at runtime; regenerate gaps (Mottainai saving partly evaporates if not).
- **Attribution correctness (FR-14):** mis-attributing an upstream break to a downstream service silently blames the wrong model — the known-broken-mesh tests (break payment/catalog) are the gate.

---

## Design-corpus pointers (where the detail lives)

| Doc | Covers |
|---|---|
| `PLAN.md` (v0.3) | The authoritative consolidated M0..M6 + deferred roadmap, effort read, OQ/risk register. |
| `REQUIREMENTS.md` (v0.3) | The FRs (substrate, fleet, journey, frontend bonus, scoring) + §0′ supersession + OQ decision record. |
| `CONTAINMENT_SPIKE.md` | §0 VERIFIED CORRECTION — why verdict B was overturned (Seatbelt denies sandboxed gRPC dial-out); the substrate split. |
| `COMPOSE_FLEET_PROTOTYPE.md` | The validated container substrate (service-DNS gRPC + `internal:true` egress-deny on macOS Docker) — the M1 seed. |
| `CONTAINERIZATION_SCOPING.md` | `build_service_image` + 5 per-language lanes + per-service cost ledger + offline-build risks — the M0 spec. |
| `NETNS_SUBSTRATE.md` | The Linux shared-netns substrate for per-service sandboxed dial-out scoring (gRPC-loopback + egress-deny). |
| `JOURNEY_DESIGN.md` (v0.2) | The transport-agnostic journey + 2 adapters (B direct-gRPC always-on / A HTTP) + bonus-frontend + canonical topology. |
| `FRONTEND_OPENAPI_CONTRACT.md` | The journey-facing HTTP contract BOTH frontends satisfy + the health/OpenAPI gate (the substitution seam). |
| `FRONTEND_LANE_SCOPING.md` | The generated-frontend seed/lane (Go reuse), its 7 deps, the bonus-scoring model + ad graceful-degrade. |
