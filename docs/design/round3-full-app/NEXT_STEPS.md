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

**Already SHIPPED / VALIDATED (start from this reality, don't rebuild):**
- **5 per-service behavioral suites + reference fixtures** — `behavioral/{catalog,email,cart,recommendation,checkout}_suite.py` (+ currency/charge/shipping/ad/pricing).
- **Startup contracts + launchers** — `resolve_serve_command`, `StartupContract`, `_DEFAULTS` for 4 langs (Java absent) — `behavioral/contract.py`.
- **Offline provisioning** — Go stubs / `.pydeps` / `dotnet publish` / node closure (`behavioral/provision.py`, `node_runtime/`).
- **Compose-fleet substrate** — PROTOTYPE, **LIVE-VALIDATED on macOS Docker** (2-svc rec→catalog, coverage 1.0, egress denied, clean teardown) — `compose-prototype/`, `tests/integration/test_compose_fleet_prototype.py`.
- **netns substrate** — PROTOTYPE, **LIVE-VALIDATED on Linux** (real gRPC + egress-deny) — `netns_substrate.py`, `tests/integration/test_netns_substrate_smoke.py`.
- **Containerization SCOPED** (5 lanes, `build_service_image`, Dockerfile patterns) and **journey + frontend DESIGNED** (no code).
- **Scorecard / runner / aggregate** — `scorecard.py`, `runner.py`, `aggregate.py`.

---

## Continue here → land M2 on `origin/main`, then M3

M1 (landed `ab12e241`) and M2 (exit criterion met) are done. M2 — journey spec + Adapter B core + m2driver + `validate_m2` — is committed on `feat/r3-m2-journey` (`1afae94b`/`fd26fc1b`/`dedf9ec7` + docs), **NOT yet pushed**.

1. **Land M2 on `origin/main`** via the contended-`main` recipe: worktree off `origin/main` → cherry-pick the M2 commits → confirm `merge-tree` clean + `merge-base --is-ancestor` → FF-push. (`origin/main` may have diverged — re-check.) Then remove the merged worktrees (`startd8-r3-m0*`, `startd8-r3-m1`, `startd8-r3-m2`).
2. **M3 — layered scoring → scorecard.** The journey already yields per-step pass/fail + the per-service attribution set (`JourneyStep.services`, dialing service first). M3 turns that into the system score: **per-step coverage** (headline, weighted by the §1 locust mix + unweighted — `adapter_b.JourneyResult` already exposes both) + **per-service fault attribution** (classify each failed step `model-fault:S` / `propagated:S←D` / `degraded:S` / `harness`) + the "canonical journey completed" boolean. Validate on the SDK-reference mesh + 2 broken meshes (break payment; break catalog) → each fault attributed to the right service+class; a downstream service never charged model-fault for an upstream break. **Reuse:** `aggregate._median/_iqr`, `scorecard.py` markdown, the verbatim-id join. The `validate_m2 --no-deps`-style stop-a-service mechanism is the broken-mesh generator. See PLAN M3.

**Reproduce M2:** `PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m2` (builds m2driver if missing, reuses the 8 backend images, runs the journey healthy + payment-stopped). Adapter B core is unit-tested (`test_adapter_b.py`, mock stubs, incl. the attribution property — no docker).

**Effectiveness practices carried through** (`craft/Lessons_Learned/sdk/lessons/01-benchmarking.md`): readiness-gated boot (#14), build-if-missing / Mottainai (#10 — M2 reused all 8 images + the m2driver across runs), invariant-based outcomes over fragile exact-oracle (#5 saturation discipline), live-proven-not-just-wired (#14 — the live run caught the `compose run` dep-revival bug the unit tests couldn't).

**Exit criterion (M2): ✅ MET** (see Status). Remaining R3 backbone: M3 (scoring) → M6 (finalists); M4/M5 frontend bonus is the parallel branch (joins at M5/M6).

**Reproduce M0 locally:** `PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m0 <go|python|node|csharp>` via backgrounded `docker build`. Node needs `node_runtime/vendor.sh` first (gitignored closure).

**Exit criterion (M0): ✅ MET + MERGED.** *Stretch (deferred to M1+):* `--network=none` hermetic build after base+cache pre-pull.

---

## Critical path

```
Track-2 contracts (DONE/scope gaps) → M0 ✅ → M1 ✅ → M2 ✅ → M3 → M6
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
