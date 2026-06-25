# Round 3 — NEXT_STEPS (cold-start runbook)

**Date:** 2026-06-24 · **Reads from:** PLAN.md v0.3 + REQUIREMENTS.md v0.3 (do not re-derive — this is a pointer/runbook)

---

## Status

Round 3 (full 9-service Online Boutique system round) is **design + plan complete** (PLAN v0.3, REQUIREMENTS v0.3 reconciled). **M0 is COMPLETE + MERGED to `origin/main`**; **M1 (compose-fleet generator) — EXIT CRITERION MET (full 8-backend fleet live-validated); NOT yet pushed** (see below).

**M0 COMPLETE + MERGED** — all 4 lanes (Go + Python + Node + C#) live-validated; landed on `origin/main` via FF-push (`2ee76f38..b2a73ef7`, cherry-picked onto diverged main per the contended-`main` rule). The two M0 worktrees (`startd8-r3-m0`, `startd8-r3-m0-python`) are now merged and can be removed.
- ✅ **Builder built** — `benchmark_matrix/fleet/containerize.py`: `build_service_image(service, workdir, language)` + `boot_and_probe(...)` + `ImageBuildResult`/`BootProbeResult`, reusing `provision.py` per language; 4 per-language templates (`fleet/templates/Dockerfile.{go,python,node,csharp}.tmpl`); injected runner (dry-run/CI-safe). `build_service_image` now takes `extra_pip` (per-service Python deps).
- ✅ **Go lane** (coverage 1.0) — 3 container bugs fixed: abspath `replace`→`./.gostubs`; `./`/`../` guard; distroless-no-`/bin/sh` (assemble `/out` in build stage).
- ✅ **Python lane (emailservice, coverage 1.0)** — 1 fix: the jinja2-rendering server import-crashed (boot ok → exit → probe 0.0) because the image lacked `jinja2`. Threaded per-service `extra_pip=["jinja2"]` (container analogue of provision's requirements.txt top-up); kept per-service, not baked into the baseline.
- ✅ **Node lane (paymentservice, coverage 1.0)** — 0 fixes (most offline-ready: vendored `node_runtime` closure staged, no npm install). Prereq: run `node_runtime/vendor.sh` (`npm ci`; `node_modules` is gitignored).
- ✅ **C# lane (cartservice, coverage 1.0)** — 2 fixes, the runbook-predicted hardest lane: **(a) arm64 protoc SIGSEGV (OQ-C4)** — Grpc.Tools 2.71's bundled `linux_arm64/protoc` exits 139 under MSBuild's `Protobuf_Compile` (`--dependency_out`), verified deterministic and NOT the OQ-C6 cold-NuGet gap; the binary is fine standalone, only the MSBuild path crashes it → build stage apt-installs `protobuf-compiler` + `-p:Protobuf_ProtocFullPath=/usr/bin/protoc`, keeping the bundled `grpc_csharp_plugin`. **(b) loopback bind** — `Program.cs` used `ListenLocalhost` (127.0.0.1 only, unreachable via published port) → `ListenAnyIP` (0.0.0.0, matches real OB; loopback behavioral path still works).
- ✅ **15 unit tests** (`tests/.../behavioral/test_containerize.py`, fake-runner/no-docker) + `fleet/validate_m0.py <lang>` (repeatable live entrypoint, all 4 lanes wired).
- ⚠️ **Tooling note:** drive docker-heavy validation in the main loop with backgrounded `docker build` (`run_in_background`) so no single call blocks for minutes. `validate_m0.py <lang>` is the entrypoint.
- ⏳ **Java deferred** (leaf, off journey; only lang with no offline build).

**M1 EXIT CRITERION MET — full 8-backend fleet live-validated; NOT yet pushed** — branch `feat/r3-m1-compose-fleet` (worktree `startd8-r3-m1`, off the M0-merged `origin/main`; commits `0dc554be`/`41766ec3`/`0056754c`/`dd1326ff`):
- ✅ **Service inventory** — `fleet/services.py`: the authoritative OB topology (JOURNEY_DESIGN §3) as `ServiceSpec(name, language, listen_port, dial_port, addr_env, deps, is_infra, image)`. **This is now the code single-source for the OB topology** (JOURNEY_DESIGN §3 is the doc source; keep them in sync — vocabulary-drift rule). Both faithfulness traps encoded in the data model: emailservice `listen 8080 / dial 5000` (`port_asymmetric`) + redis-cart `is_infra` sidecar. `topo_order()` = dependency-ordered bring-up, rejects cycles/unknown deps. v1 = 8 backends + redis (adservice/Java deferred; frontend = M4).
- ✅ **Compose generator** — `fleet/compose.py`: `generate_compose_dict/_yaml` → `internal:true` `fleet` net (egress-deny + service-DNS), optional `edge` bridge for a host-reachable ingress, each dep edge as `{ADDR_ENV}: peer:dial_port`, redis sidecar, email `PORT=dial_port`, `depends_on` ordering, M0-matching image tags `r3/<svc>:<lang>`.
- ✅ **14 no-docker unit tests** (`tests/unit/benchmark_matrix/test_compose_fleet.py`) — inventory, both traps, topo order (+ cycle/unknown-dep rejection), internal net, service-DNS wiring, redis sidecar, ingress edge/host-port, YAML round-trip.
- ✅ **Readiness-gate fix** (`41766ec3`) — `boot_and_probe` now means "serving" (port accepts), not "docker run returned an id"; drops `--rm` so a crashed container's logs survive; +2 tests; live-reproven on the go lane. De-risks fleet bring-up.
- ✅ **Live substrate PROVEN** (`validate_m1.py`, `0056754c`) — build-if-missing → `generate_compose` → `up` → readiness + service-DNS + egress-deny (from an alpine probe sidecar; the M0 Go image is distroless, no in-container shell) → clean teardown. **Two live PASSes on macOS Docker:** default `{productcatalog, recommendation}` (recommendation built fresh, 0 fixes); expanded `{cart, email, payment, recommendation}` = **5 backends / 4 languages + redis-cart**, with **both faithfulness traps validated end-to-end** — emailservice ready on `:5000` (port asymmetry) and `service-DNS redis-cart:6379 OK` (sidecar). Egress denied + clean teardown both runs.
- ✅ **shipping + currency reference servers authored** (`dd1326ff`) — the 2 previously-missing backends. `shipping_reference/main.go` (Go: GetQuote deterministic non-negative USD + ShipOrder) and `currency_reference/server.js` (Node: Convert EUR-base rate table w/ exact same-currency identity + integer-nano normalization + unknown-code reject, GetSupportedCurrencies). Both **coverage 1.0** via new `validate_m0 {shipping,currency}` lanes, 0 server fixes. All 8 backends now buildable.
- ✅ **FULL 8-BACKEND FLEET — M1 EXIT CRITERION MET** (`validate_m1 --subset checkoutservice,recommendationservice`): 8 backends + redis-cart (9 services, 5 languages) all ready; **checkout's full 6-dep fan-out resolved over service-DNS** (productcatalog/shipping/payment/email/currency/cart) + cart→redis + rec→catalog; email on `:5000` (asymmetry); **egress to 1.1.1.1:443 DENIED**; clean teardown leaves zero containers/networks. checkout built fresh, 0 fixes.
- ✅ **M1 LANDED on `origin/main`** (FF `c0f8f3af..ab12e241`).

**M2 EXIT CRITERION MET — Adapter B live over the full mesh; NOT yet pushed** — branch `feat/r3-m2-journey` (worktree `startd8-r3-m2`, off the M1-merged `origin/main`; commits `1afae94b`/`fd26fc1b`/`dedf9ec7` + docs):
- ✅ **Journey spec** — `fleet/journey.py`: the defined-once transport-agnostic 5-step journey (browse→setCurrency→addToCart→viewCart→checkout) as `JourneyStep(name, intent, outcome, services, weight)`; weights = §1 locust mix (browse 10 dominant; checkout 1 deep); each step's `services` = the M3 per-service attribution set; canonical future-dated checkout payload reused verbatim by both adapters. (+TRY added to the currency server so the full setCurrency whitelist is supported.)
- ✅ **Adapter B core** — `fleet/adapter_b.py`: the direct-gRPC driver replaying the 5 steps' fan-out, scoring invariant-based per-step outcomes (weighted + unweighted coverage) + per-service attribution; `run_journey_with_stubs` (injectable, unit-tested) / `run_journey(addr_map)` (live) / `__main__` (in-fleet driver-container entrypoint, prints per-step JSON). **11 M2 unit tests** incl. the KEY attribution property: healthy mesh = coverage 1.0; break payment → ONLY checkout fails.
- ✅ **LIVE — M2 EXIT CRITERION MET** (`validate_m2`, `dedf9ec7`): the `m2driver` container (python+grpc, runs `adapter_b` on the fleet net, dials by service-DNS, prints per-step JSON — egress-deny preserved). **Healthy mesh = coverage 1.00** (all 5 steps pass end-to-end: browse; setCurrency→EUR; addToCart; viewCart w/ live shipping quote; checkout order_id). **Break payment (`compose stop paymentservice`) → `failed=['checkout']`** — only checkout fails (live per-service attribution). Harness bug caught+fixed live: `compose run` was reviving the stopped dep → `--no-deps`. Confirmed `checkout_reference` is a real 6-dep orchestrator.
- ✅ **M2 LANDED on `origin/main`** (FF `0c810feb..cd4ae11b`).

**M3 EXIT CRITERION MET + MERGED — layered scoring + per-service attribution, live on 3 meshes** (FF `c642fedb..be9e9783`):
- ✅ **Culprit-aware Adapter B** — `adapter_b.py`: each failed step names the responsible service (a `_rpc(service, fn)` helper tags RPC errors; direct steps return the broken service; the checkout step parses the orchestrator's wrapped error — `charge:`→payment, `getproduct:`→catalog, … — so a checkout failure names the failing DEP). `StepResult.culprit`; `journey.py` `JourneyStep.orchestrated` (checkout only).
- ✅ **Scorer** — `fleet/score.py`: `score_journey(JourneyResult) → Scorecard` (per-step coverage weighted+unweighted; per-service attribution `model-fault`/`propagated`/`harness`; `journey_completed` FR-13; `confidence` low-when-all-fail FR-22). A downstream-dep break of an orchestrated step → **model-fault on the dep + propagated (NOT model-fault) on checkoutservice**. Pure function, unit-tested.
- ✅ **LIVE (`validate_m3`)** — run + score on the reference mesh + 2 broken meshes: **reference** coverage 1.00, no model-fault; **break payment** → `model-fault: paymentservice` + `propagated: checkoutservice via paymentservice`; **break catalog** → `model-fault: productcatalogservice` + `propagated: checkoutservice`. Checkout NEVER charged for an upstream break (the load-bearing M3 rule), live on both. **32 M1/M2/M3 unit tests pass.**

**M6 EXIT CRITERION MET — system report + decision gate; R3 BACKBONE M0→M6 COMPLETE; NOT yet pushed** — branch `feat/r3-m6-finalists` (worktree `startd8-r3-m6`, off the M3-merged `origin/main`; commits `220e398a`):
- ✅ **Report + ranking + gate** — `fleet/report.py`: `FinalistScore` + `rank_finalists` (system score = weighted per-step coverage desc; tie-break fewer own model-faults, then cost) + `DecisionGate` (advisory FR-21 — **GO iff the journey DISCRIMINATES finalists AND attribution is TRUSTWORTHY**) + `build_system_report → (json, markdown leaderboard)`. Pure functions over `Scorecard`. **7 unit tests** (rank, tie-breaks, GO/NO-GO for tie / untrustworthy / single-finalist, render).
- ✅ **LIVE capstone (`validate_m6`)** — proves the END-TO-END M0→M6 pipeline emits `round3-system-report.{json,md}` from LIVE Scorecards. Drove the reference fleet in 3 configs as discriminating finalists: **`reference` 1.000 > `reference-no-payment` 0.944 > `reference-no-catalog` 0.278** (the browse-heavy §1 weighting makes a catalog break far more damaging than a payment break — the weighting discriminates as intended); per-finalist model-faults attributed correctly; **decision gate GO** (spread 0.722, attribution trustworthy). A real benchmark run feeds distinct MODEL fleets into the same report path.

**Already SHIPPED / VALIDATED (start from this reality, don't rebuild):**
- **5 per-service behavioral suites + reference fixtures** — `behavioral/{catalog,email,cart,recommendation,checkout}_suite.py` (+ currency/charge/shipping/ad/pricing).
- **Startup contracts + launchers** — `resolve_serve_command`, `StartupContract`, `_DEFAULTS` for 4 langs (Java absent) — `behavioral/contract.py`.
- **Offline provisioning** — Go stubs / `.pydeps` / `dotnet publish` / node closure (`behavioral/provision.py`, `node_runtime/`).
- **Compose-fleet substrate** — PROTOTYPE, **LIVE-VALIDATED on macOS Docker** (2-svc rec→catalog, coverage 1.0, egress denied, clean teardown) — `compose-prototype/`, `tests/integration/test_compose_fleet_prototype.py`.
- **netns substrate** — PROTOTYPE, **LIVE-VALIDATED on Linux** (real gRPC + egress-deny) — `netns_substrate.py`, `tests/integration/test_netns_substrate_smoke.py`.
- **Containerization SCOPED** (5 lanes, `build_service_image`, Dockerfile patterns) and **journey + frontend DESIGNED** (no code).
- **Scorecard / runner / aggregate** — `scorecard.py`, `runner.py`, `aggregate.py`.

---

## Continue here → land M6, then the remaining wiring / parallel branch

The R3 **backbone M0→M6 is COMPLETE and live-proven end-to-end** (M0–M3 landed; M6 — `report.py` + `validate_m6` capstone — committed on `feat/r3-m6-finalists` (`220e398a`), **NOT yet pushed**). The harness builds 8-backend polyglot fleets, drives the journey, scores per-step coverage with honest per-service attribution, and emits a ranked advisory system report with a decision gate.

1. **Land M6 on `origin/main`** via the contended-`main` recipe: worktree off `origin/main` → cherry-pick → `merge-tree` clean + `merge-base --is-ancestor` → FF-push. Then remove the merged worktrees (`startd8-r3-m0*` … `startd8-r3-m6`).
2. **Remaining to a real benchmark run** (thin, mostly wiring):
   - **`startd8 benchmark round3` CLI** + **roster resolver** (`roster.py`): resolve a finalist roster (model ids → each model's `r3/<model>/<svc>` fleet images), run `validate_m1/m2/m3` per finalist, build the report. The report/ranking/gate path is done — this is the orchestration wrapper.
   - **Per-finalist fleets** — the actual model-generated 9-service workdirs (reuse by verbatim model id, regenerate gaps — OQ-3; real LLM spend). Persist per-cell (Mottainai → $0 rescore).
   - **Cost/speed columns** — wire the per-model `cost_usd`/`wall_seconds` into `FinalistScore` from the generation run.
3. **M4/M5 frontend BONUS** (parallel branch, never on the critical path): seed + health/OpenAPI gate + canonical substitution + Adapter A → additive capped bonus column in the report.

**Reproduce M6:** `PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m6` (force-rebuilds the driver, reuses the 8 images, drives 3 configs, writes `round3-system-report.{json,md}`). Report/ranking/gate unit-tested (`test_report.py` — no docker).

**Effectiveness practices carried through the whole backbone** (`craft/Lessons_Learned/sdk/lessons/01-benchmarking.md`): readiness-gated boot (#14), build-if-missing / Mottainai (#10 — M6 reused all 8 images), invariant-based attribution + the journey's earlier steps as per-service liveness probes, weighted coverage by the §1 locust mix (a catalog break scores far worse than a payment break — the weighting discriminates), live-proven-not-just-wired (#14 — every milestone caught real bugs only the live run could: jinja2/ListenLocalhost/arm64-protoc/compose-run-dep-revival).

**Exit criterion (M3): ✅ MET** (see Status). Remaining R3 backbone: **M6** (finalists + report). M4/M5 frontend bonus is the parallel branch (joins at M5/M6).

**Reproduce M0 locally:** `PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m0 <go|python|node|csharp>` via backgrounded `docker build`. Node needs `node_runtime/vendor.sh` first (gitignored closure).

**Exit criterion (M0): ✅ MET + MERGED.** *Stretch (deferred to M1+):* `--network=none` hermetic build after base+cache pre-pull.

---

## Critical path

```
Track-2 contracts (DONE/scope gaps) → M0 ✅ → M1 ✅ → M2 ✅ → M3 ✅ → M6 ✅  (backbone COMPLETE)
                                                    └ M4 → M5  (frontend BONUS — PARALLEL branch, joins at M5/M6, NEVER on the critical path)
```
The frontend bonus branch can never block backend scoring — that is the whole point of the substitution seam.

---

## Per-milestone one-liners (goal · exit · effort — from PLAN v0.3)

| M | Goal | Exit criterion | Effort |
|---|---|---|---|
| **M0** ✅ | `build_service_image` + Go/Python/Node/C# Dockerfiles | runnable image per lang from a workdir; boots + 1 RPC. **DONE — all 4 lanes live (coverage 1.0): Go (3 fixes), Python (jinja2 extra_pip), Node (0), C# (arm64 protoc + ListenAnyIP)** | done |
| **M1** ✅ | N-service compose-fleet generator (8/9 backends, egress-denied, service-DNS) | **MET** — full 8-backend fleet + redis (9 svc, 5 langs) boots on macOS Docker; every `*_SERVICE_ADDR` resolves (checkout's 6-dep fan-out); egress to 1.1.1.1:443 DENIED; clean teardown. Generator + readiness-gate + `validate_m0/m1` + 2 new reference servers. **Not yet pushed.** | done |
| **M2** ✅ | Transport-agnostic journey + Adapter B (direct-gRPC, always-on) | **MET** — Adapter B over the live 9-svc mesh = 100% step coverage; break payment → only checkout's step fails. journey spec + adapter_b + m2driver + validate_m2 (25 unit + live). **Not yet pushed.** | done |
| **M3** ✅ | Layered scoring → scorecard (per-step coverage + per-service fault attribution + journey-completed bool) | **MET** — live on SDK-ref + break-payment + break-catalog meshes: each fault attributed to the right service+class; checkout never charged model-fault for an upstream break; all-degrade → low-confidence. score.py + culprit-aware adapter_b + validate_m3 (32 unit + live). **Not yet pushed.** | done |
| **M4** | Frontend BONUS lane (seed + health/OpenAPI gate + canonical substitution + Adapter A) | a subtly-broken frontend (confirmation w/o real order id) FAILS gate + falls to canonical cleanly; Adapter A green over canonical; report records which ran + verdict | ~1 |
| **M5** | Frontend bonus → scorecard (additive, capped) | brilliant-frontend/weak-backend model never outranks strong-backend; bonus = labeled "+frontend" tie-break; substituted runs show `frontend_bonus=0` | ~¼ |
| **M6** ✅ | Real finalists (single-model fleets) + system report + CLI + decision gate | **MET (harness)** — `report.py` (rank + advisory gate) + `validate_m6` capstone: live 3-config finalists ranked by system score, attribution columns, decision gate GO (discriminates + trustworthy), `round3-system-report.{json,md}` emitted. **A real benchmark run feeds distinct model fleets into the same path; `startd8 benchmark round3` CLI wrapper is the remaining thin wiring.** Not yet pushed. | done (harness) |

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
- **C# warm-NuGet bake (OQ-C6):** still the unsolved OFFLINE reuse gap — `dotnet restore` is the only network step; cold cache breaks an offline build. Bake+snapshot `~/.nuget`, then `--no-restore` publish. (M0 builds with network; confirmed NOT the cause of the C# build failure — restore succeeded in ~6-12s.)
- **arm64 vs amd64 (OQ-C4):** dep caches are arch-specific; build per-target-arch (Node closure is portable). **RESOLVED for C# M0:** Grpc.Tools 2.71's bundled `linux_arm64/protoc` SIGSEGVs (139) under MSBuild's `Protobuf_Compile` (`--dependency_out`) — deterministic; the build now uses the apt system protoc via `Protobuf_ProtocFullPath` (harmless on amd64 where the bundled protoc works). If a future move to amd64-only CI builds makes this moot, the override can be dropped on amd64.
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
