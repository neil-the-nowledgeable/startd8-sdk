# Round 3 — NEXT_STEPS (cold-start runbook)

**Date:** 2026-06-24 · **Reads from:** PLAN.md v0.3 + REQUIREMENTS.md v0.3 (do not re-derive — this is a pointer/runbook)

---

## Status

Round 3 (full 9-service Online Boutique system round) is **design + plan complete** (PLAN v0.3, REQUIREMENTS v0.3 reconciled). **M0 is COMPLETE + MERGED to `origin/main`**; **M1 (compose-fleet generator) is IN PROGRESS — generator core done, live validation pending** (see below).

**M0 COMPLETE + MERGED** — all 4 lanes (Go + Python + Node + C#) live-validated; landed on `origin/main` via FF-push (`2ee76f38..b2a73ef7`, cherry-picked onto diverged main per the contended-`main` rule). The two M0 worktrees (`startd8-r3-m0`, `startd8-r3-m0-python`) are now merged and can be removed.
- ✅ **Builder built** — `benchmark_matrix/fleet/containerize.py`: `build_service_image(service, workdir, language)` + `boot_and_probe(...)` + `ImageBuildResult`/`BootProbeResult`, reusing `provision.py` per language; 4 per-language templates (`fleet/templates/Dockerfile.{go,python,node,csharp}.tmpl`); injected runner (dry-run/CI-safe). `build_service_image` now takes `extra_pip` (per-service Python deps).
- ✅ **Go lane** (coverage 1.0) — 3 container bugs fixed: abspath `replace`→`./.gostubs`; `./`/`../` guard; distroless-no-`/bin/sh` (assemble `/out` in build stage).
- ✅ **Python lane (emailservice, coverage 1.0)** — 1 fix: the jinja2-rendering server import-crashed (boot ok → exit → probe 0.0) because the image lacked `jinja2`. Threaded per-service `extra_pip=["jinja2"]` (container analogue of provision's requirements.txt top-up); kept per-service, not baked into the baseline.
- ✅ **Node lane (paymentservice, coverage 1.0)** — 0 fixes (most offline-ready: vendored `node_runtime` closure staged, no npm install). Prereq: run `node_runtime/vendor.sh` (`npm ci`; `node_modules` is gitignored).
- ✅ **C# lane (cartservice, coverage 1.0)** — 2 fixes, the runbook-predicted hardest lane: **(a) arm64 protoc SIGSEGV (OQ-C4)** — Grpc.Tools 2.71's bundled `linux_arm64/protoc` exits 139 under MSBuild's `Protobuf_Compile` (`--dependency_out`), verified deterministic and NOT the OQ-C6 cold-NuGet gap; the binary is fine standalone, only the MSBuild path crashes it → build stage apt-installs `protobuf-compiler` + `-p:Protobuf_ProtocFullPath=/usr/bin/protoc`, keeping the bundled `grpc_csharp_plugin`. **(b) loopback bind** — `Program.cs` used `ListenLocalhost` (127.0.0.1 only, unreachable via published port) → `ListenAnyIP` (0.0.0.0, matches real OB; loopback behavioral path still works).
- ✅ **15 unit tests** (`tests/.../behavioral/test_containerize.py`, fake-runner/no-docker) + `fleet/validate_m0.py <lang>` (repeatable live entrypoint, all 4 lanes wired).
- ⚠️ **Tooling note:** drive docker-heavy validation in the main loop with backgrounded `docker build` (`run_in_background`) so no single call blocks for minutes. `validate_m0.py <lang>` is the entrypoint.
- ⏳ **Java deferred** (leaf, off journey; only lang with no offline build).

**M1 IN PROGRESS — generator + readiness-gate + live substrate proven; full 8-svc fleet gated on 2 reference servers** — branch `feat/r3-m1-compose-fleet` (worktree `startd8-r3-m1`, off the M0-merged `origin/main`; commits `0dc554be`/`41766ec3`/`0056754c`, NOT pushed):
- ✅ **Service inventory** — `fleet/services.py`: the authoritative OB topology (JOURNEY_DESIGN §3) as `ServiceSpec(name, language, listen_port, dial_port, addr_env, deps, is_infra, image)`. **This is now the code single-source for the OB topology** (JOURNEY_DESIGN §3 is the doc source; keep them in sync — vocabulary-drift rule). Both faithfulness traps encoded in the data model: emailservice `listen 8080 / dial 5000` (`port_asymmetric`) + redis-cart `is_infra` sidecar. `topo_order()` = dependency-ordered bring-up, rejects cycles/unknown deps. v1 = 8 backends + redis (adservice/Java deferred; frontend = M4).
- ✅ **Compose generator** — `fleet/compose.py`: `generate_compose_dict/_yaml` → `internal:true` `fleet` net (egress-deny + service-DNS), optional `edge` bridge for a host-reachable ingress, each dep edge as `{ADDR_ENV}: peer:dial_port`, redis sidecar, email `PORT=dial_port`, `depends_on` ordering, M0-matching image tags `r3/<svc>:<lang>`.
- ✅ **14 no-docker unit tests** (`tests/unit/benchmark_matrix/test_compose_fleet.py`) — inventory, both traps, topo order (+ cycle/unknown-dep rejection), internal net, service-DNS wiring, redis sidecar, ingress edge/host-port, YAML round-trip.
- ✅ **Readiness-gate fix** (`41766ec3`) — `boot_and_probe` now means "serving" (port accepts), not "docker run returned an id"; drops `--rm` so a crashed container's logs survive; +2 tests; live-reproven on the go lane. De-risks fleet bring-up.
- ✅ **Live substrate PROVEN** (`validate_m1.py`, `0056754c`) — build-if-missing → `generate_compose` → `up` → readiness + service-DNS + egress-deny (from an alpine probe sidecar; the M0 Go image is distroless, no in-container shell) → clean teardown. **Two live PASSes on macOS Docker:** default `{productcatalog, recommendation}` (recommendation built fresh, 0 fixes); expanded `{cart, email, payment, recommendation}` = **5 backends / 4 languages + redis-cart**, with **both faithfulness traps validated end-to-end** — emailservice ready on `:5000` (port asymmetry) and `service-DNS redis-cart:6379 OK` (sidecar). Egress denied + clean teardown both runs.
- ⏳ **Full 8-svc fleet (the M1 exit criterion) gated on 2 reference servers** — only services with a buildable reference fixture can join: today `{productcatalog, checkout, cart, email, payment, recommendation}`. **`shippingservice` (go) + `currencyservice` (node) reference servers do not exist yet**, so the full 8-backend fleet AND checkout's 6-dep fan-out are blocked until they're authored. See "Continue here".

**Already SHIPPED / VALIDATED (start from this reality, don't rebuild):**
- **5 per-service behavioral suites + reference fixtures** — `behavioral/{catalog,email,cart,recommendation,checkout}_suite.py` (+ currency/charge/shipping/ad/pricing).
- **Startup contracts + launchers** — `resolve_serve_command`, `StartupContract`, `_DEFAULTS` for 4 langs (Java absent) — `behavioral/contract.py`.
- **Offline provisioning** — Go stubs / `.pydeps` / `dotnet publish` / node closure (`behavioral/provision.py`, `node_runtime/`).
- **Compose-fleet substrate** — PROTOTYPE, **LIVE-VALIDATED on macOS Docker** (2-svc rec→catalog, coverage 1.0, egress denied, clean teardown) — `compose-prototype/`, `tests/integration/test_compose_fleet_prototype.py`.
- **netns substrate** — PROTOTYPE, **LIVE-VALIDATED on Linux** (real gRPC + egress-deny) — `netns_substrate.py`, `tests/integration/test_netns_substrate_smoke.py`.
- **Containerization SCOPED** (5 lanes, `build_service_image`, Dockerfile patterns) and **journey + frontend DESIGNED** (no code).
- **Scorecard / runner / aggregate** — `scorecard.py`, `runner.py`, `aggregate.py`.

---

## Continue here → author shipping + currency reference servers → full 8-svc fleet → land M1

The generator, the readiness-gate fix, and live `validate_m1` are **done and proven** on the buildable subset (5 backends / 4 languages + redis, both faithfulness traps validated live). The M1 **exit criterion** ("SDK-reference 8-service fleet boots; every `*_SERVICE_ADDR` resolves; egress denied; clean teardown") is **gated on two missing reference servers**:

1. **Author `shippingservice` (Go) + `currencyservice` (Node) reference servers** — the only 2 of the 8 backends without a `*_reference` fixture. Mirror the existing reference servers (`catalog_reference/main.go` for Go shape; `payment_reference/server.js` for Node) + their behavioral suites (`shipping_suite`, `currency_suite` already exist). Each is a small gRPC server reading `$PORT`, binding `0.0.0.0` (NOT loopback — the C# `ListenLocalhost` lesson), serving its OB RPC (ShipOrder/GetQuote; Convert/GetSupportedCurrencies). Add a `validate_m1` build recipe + a `validate_m0`-style lane for each.
2. **Run the full 8-service fleet** `validate_m1 --subset checkoutservice` (dependency-closure pulls in all 6 checkout deps + redis). This exercises checkout's 6-dep fan-out — the journey's deepest node — over real service-DNS. This is the M1 exit gate.
3. **Land M1 on `origin/main`** via the contended-`main` recipe (worktree off `origin/main` → cherry-pick the M1 commits → confirm `merge-tree` clean + `merge-base --is-ancestor` → FF-push), then proceed to **M2** (transport-agnostic journey + Adapter B over the live fleet — Adapter B replays checkout's fan-out against the live mesh, the natural next step now that the fleet stands up).

**Effectiveness practices already baked into `validate_m1`** (`craft/Lessons_Learned/sdk/lessons/01-benchmarking.md`): readiness-gated boot (#14), build-if-missing / Mottainai (#10), `--subset` quick mode (#1), generator-inert-until-live-proven (#14 "wired ≠ working" — M1 not done on the generator alone). Still available to add: **parallelize the image builds** (independent; currently serial) for the full-fleet cold build.

**Reproduce M0 locally:** `PYTHONPATH=src python3 -m startd8.benchmark_matrix.fleet.validate_m0 <go|python|node|csharp>` via backgrounded `docker build`. Node needs `node_runtime/vendor.sh` first (gitignored closure).

**Exit criterion (M0): ✅ MET + MERGED.** *Stretch (deferred to M1+):* `--network=none` hermetic build after base+cache pre-pull.

---

## Critical path

```
Track-2 contracts (DONE/scope gaps) → M0 ✅ → M1 → M2 → M3 → M6
                                                    └ M4 → M5  (frontend BONUS — PARALLEL branch, joins at M5/M6, NEVER on the critical path)
```
The frontend bonus branch can never block backend scoring — that is the whole point of the substitution seam.

---

## Per-milestone one-liners (goal · exit · effort — from PLAN v0.3)

| M | Goal | Exit criterion | Effort |
|---|---|---|---|
| **M0** ✅ | `build_service_image` + Go/Python/Node/C# Dockerfiles | runnable image per lang from a workdir; boots + 1 RPC. **DONE — all 4 lanes live (coverage 1.0): Go (3 fixes), Python (jinja2 extra_pip), Node (0), C# (arm64 protoc + ListenAnyIP)** | done |
| **M1** ⏳ | N-service compose-fleet generator (8/9 backends, egress-denied, service-DNS) | SDK-ref 8-svc fleet boots on macOS Docker; every `*_SERVICE_ADDR` resolves; egress to 1.1.1.1:443 DENIED; teardown leaves zero containers. **Generator + readiness-gate + live `validate_m1` ✅ (5-backend/4-lang+redis subset, both traps proven); full 8-svc gated on authoring shipping+currency reference servers** | ~1 (+¼ for 2 servers) |
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
