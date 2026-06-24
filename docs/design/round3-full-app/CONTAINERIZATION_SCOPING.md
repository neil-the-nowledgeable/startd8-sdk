# Round 3 — Per-Language Containerization Scoping

**Version:** 0.1 (scoping only — NO implementation)
**Date:** 2026-06-24
**Status:** Design/requirements scoping. The deliverable is the per-language cost ledger + cross-cutting
risks + a recommended approach. No code in this pass.
**Owner SDK area:** `startd8.benchmark_matrix.behavioral` (provisioning reuse) + a NET-NEW
`benchmark_matrix.containers` build layer + Round-3 fleet orchestrator.
**Parents:**
- `docs/design/round3-full-app/REQUIREMENTS.md` (Round 3 system round; v0.2)
- `docs/design/round3-full-app/CONTAINMENT_SPIKE.md` (verdict B — Seatbelt loopback fleet, no Docker in v1)
- `docs/design/round3-full-app/NETNS_SUBSTRATE.md` (the bare-process substrate this doc costs *against*)

---

## 0. Why this exists (substrate decision recap)

Round 3 deploys each contestant model's full 9-service Online Boutique fleet **together** and scores
cross-service journeys. The containment spike (verdict B) showed the existing macOS Seatbelt sandbox
co-runs the fleet over a shared loopback plane with no Docker — so **v1 ships on the bare-process
netns/Seatbelt substrate**. This doc scopes the **next** substrate: **per-service containers
(docker-compose first, kind later)** — the most faithful real-world environment, where:

- Container-to-container gRPC works under default seccomp; **egress denied at the NETWORK layer**
  (Docker `--internal` network / k8s `NetworkPolicy`), not by per-process Seatbelt. Default container
  hardening is **KEPT** for the untrusted generated services.
- The harness must **provide the build scaffolding** — a model generates only SERVICE SOURCE, usually
  with **no Dockerfile / go.mod / package.json / csproj / pom.xml**. The container build is the
  harness's job: it wraps the generated source + offline deps + the OB gRPC stubs.
- **Hermeticity is a hard requirement.** The image build must work **OFFLINE** (no network at build
  or run). Same discipline already enforced for offline provisioning (`provision.py`, node closure).

This is the **real new cost** versus the bare-process approach. Everything below estimates it.

---

## 1. Confirmed service ↔ language map (from `seeds/seeds-index.json`)

9 core services, 5 languages. Map is **pinned** (FR-31 cross-language comparability — language is fixed
per service across all models/reps). Each service's startup launcher is already resolved in
`behavioral/contract.py`; its container CMD derives directly from that launcher.

| Service | Language | Target file (seed) | RPCs | Existing stub/dep asset it reuses |
|---|---|---|---|---|
| productcatalogservice | **Go** | `src/productcatalogservice/server.go` | ListProducts/GetProduct/Search | `go_stubs/hipstershop/*.pb.go` + `setup_go_stubs` |
| checkoutservice | **Go** | `src/checkoutservice/main.go` | PlaceOrder | same Go stubs; 6 `*_SERVICE_ADDR` deps |
| shippingservice | **Go** | `src/shippingservice/main.go` | GetQuote/ShipOrder | same Go stubs |
| recommendationservice | **Python** | `src/recommendationservice/recommendation_server.py` | ListRecommendations | `demo_pb2*.py` + `.pydeps` (grpcio/protobuf) |
| emailservice | **Python** | `src/emailservice/email_server.py` | SendOrderConfirmation | `demo_pb2*.py` + `.pydeps` + Jinja2 |
| cartservice | **C#** | `src/cartservice/src/services/CartService.cs` | AddItem/GetCart/EmptyCart | `Grpc.Tools` codegen + `publish_dotnet_service` |
| currencyservice | **Node.js** | `src/currencyservice/server.js` | Convert/GetSupportedCurrencies | `node_runtime/node_modules` + `prepare_node_workdir` |
| paymentservice | **Node.js** | `src/paymentservice/server.js` | Charge | same node closure (+ `charge_suite` ground truth) |
| adservice | **Java** | `src/adservice/src/main/java/hipstershop/AdService.java` | GetAds | **none yet** — Java provisioning is unbuilt (degrade today) |

Hardened variants (currency, payment — both Node) reuse the same node lane. **Java (adservice) is the
only language with zero existing offline-build support** (provision.py `install_plan` returns None for
java; contract.py has no `_java_default`). Counts: **Go 3 / Python 2 / Node 2 / C# 1 / Java 1.**

Note: `frontend` and `loadgenerator` are **not seeds** (NR-2) — the journey driver is SDK-authored.
So the containerized fleet is **9 backend services**, no frontend image.

---

## 2. Per-language Dockerfile scope

Each row = one parameterized Dockerfile template. "REUSE" = the offline-dep story already exists in
the harness and the Dockerfile build stage just shells the same logic; "NET-NEW" = genuinely new work.
Upstream OB Dockerfiles (found in the go-mod cache, `microservices-demo@v0.10.5/src/*/Dockerfile`) are
**reference templates only** — they pull from the network and target the canonical impl, so they are a
*pattern*, not a drop-in.

| Lang | Base image (build → runtime) | OB gRPC stubs into image | Offline dep vendoring | Run CMD (from contract.py) | Port/env | REUSE vs NET-NEW |
|---|---|---|---|---|---|---|
| **Go** | `golang:1.21` builder → `gcr.io/distroless/static` (or scratch) runtime; static binary | copy `go_stubs/hipstershop/*.pb.go` as a **local module** + go.mod `replace` (exactly `setup_go_stubs`) | `GOFLAGS=-mod=mod`, `GOMODCACHE` pre-seeded into build context; `go build -o .bin/server` at build (same as prepare-time today) | `./server` (binary) | `PORT` env; gRPC :3550/:5050/:7000 → compose DNS `productcatalogservice:PORT` | **REUSE** (stub vendoring + build already exist) |
| **Python** | `python:3.x-slim` (single-stage ok; or builder for wheels) | copy `demo_pb2.py`+`demo_pb2_grpc.py` into svc dir | copy pre-built `.pydeps` (grpcio/protobuf/typing_extensions + Jinja2 for email) into image; `--only-binary` wheel set baked into build context | `python3 <entry>.py` | `PORT` env → compose DNS | **REUSE** (.pydeps + stubs exist) |
| **Node** | `node:20-alpine` runtime (no build stage needed — closure is vendored) | proto-loader loads `demo.proto` at runtime (copy proto in); no codegen | copy `node_runtime/node_modules` closure (grpc-js/proto-loader/pino/uuid/decimal.js) into image | `node <entry>.js` | `PORT` env → compose DNS | **REUSE** (full vendored closure exists) |
| **C#** | `dotnet/sdk` builder (publish) → `dotnet/runtime-deps` chiseled runtime | `Grpc.Tools` codegen from co-located `demo.proto` during `dotnet publish` | **NuGet restore** — needs a pre-populated `~/.nuget` cache baked into the build context (cold cache = network) | `dotnet ./server.dll` | `PORT` + `ASPNETCORE_URLS=http://0.0.0.0:PORT` | **PARTLY REUSE** (`publish_dotnet_service` exists, but its offline-NuGet story is unsolved) |
| **Java** | `eclipse-temurin:jdk` builder → `temurin:jre` runtime | protobuf-gradle-plugin OR vendored javac stubs from `demo.proto` | **maven/gradle offline** — needs a pre-populated `~/.m2` / gradle cache; upstream uses `./gradlew downloadRepos` (network) | `java -jar` / `bin/AdService` | gRPC :9555 → compose DNS | **NET-NEW** (no Java provisioning exists at all) |

The injected-build-files problem (every language lacks them in generated source) is §4.

---

## 3. Hardest offline-build cases (ranked)

1. **Java (adservice) — hardest, and net-new.** No existing provisioning (`install_plan` returns None,
   no `_java_default` launcher). Upstream builds with **gradle** (`./gradlew downloadRepos` +
   `installDist`) — gradle/maven both **fetch from the network on a cold cache AND execute untrusted
   build scripts** (the FR-P1-SEC-1 hazard provision.py deliberately avoids for C#). Offline Java needs
   either a pre-seeded `~/.m2`/gradle cache baked into the build context *plus* a way to compile without
   running the model's `build.gradle` (the secure path = `javac` over vendored jars + protobuf stubs,
   mirroring the C# "publish not run" stance). This is a whole new lane. **Recommend: defer adservice to
   v2** (it is 1 leaf service, GetAds, not on the canonical browse→cart→checkout→payment journey).

2. **C# (cartservice) — second hardest, partially solved.** `publish_dotnet_service` exists but its
   docstring is explicit: `dotnet publish` runs a **NuGet restore that needs network on a cold cache**;
   `offline=True` fails closed. For a hermetic image we must **bake a warm NuGet cache into the build
   context** (pre-restore the cartservice deps once, snapshot `~/.nuget/packages`, copy into the builder
   stage, `dotnet publish --no-restore` style). Grpc.Tools codegen runs inside publish — fine once the
   cache is warm. Also `PublishTrimmed`/self-contained from upstream is heavy; framework-dependent is
   smaller and the harness already targets that.

3. **Go stub asymmetry (already solved, but the trap to preserve).** Go is otherwise easy, but the
   reason it *needs* `setup_go_stubs` is the documented trap: a model imports
   `github.com/GoogleCloudPlatform/microservices-demo/...` but leaves go.mod bare, so `go mod tidy`
   chases `@latest` (which dropped the `hipstershop` package) and **fails offline**. The Dockerfile MUST
   replicate the local-module + `replace` injection before `go build`, or Go becomes a hard case too.
   Reusing `setup_go_stubs` verbatim keeps it easy.

Python and Node are **not hard** — both have complete offline closures today (`.pydeps`, vendored
`node_modules`). They become "copy the closure into the image" with no network.

---

## 4. The generated-code-lacks-build-files problem

The model emits **source only** (a `server.go`, `server.js`, `CartService.cs`, etc.) and usually no
build manifest. The harness must **inject the build files around the generated source** — exactly what
`provision.py` already does at prepare time, lifted into a Docker build context:

- **Go:** synthesize/repair `go.mod` (the fixture provides a stub one), then `setup_go_stubs` injects
  the local stub module + `require`/`replace`. Inject a minimal `Dockerfile` with the golang builder.
- **Python:** the entry already runs under `python3`; inject `demo_pb2*.py`, `.pydeps`, and a
  `requirements.txt` top-up only if the model declared one. Dockerfile copies `.pydeps` onto PYTHONPATH.
- **Node:** inject the vendored `node_modules` + `demo.proto`; the model's `package.json` (if any) is
  advisory — the closure is authoritative. Dockerfile copies the closure in.
- **C#:** inject a harness-owned `.csproj` (with `Grpc.Tools` + `<AssemblyName>server</AssemblyName>` +
  `demo.proto` as a `<Protobuf>` item) around the generated `.cs`. Dockerfile = sdk builder publishing
  against the warm NuGet cache → runtime image.
- **Java (v2):** inject `build.gradle`/`pom.xml` + protobuf plugin config + a warm `~/.m2`.

**This composes cleanly with §provisioning:** the Dockerfile build stage is just `provision.py`'s logic
relocated. The harness owns the build manifests; the model owns only the source. This is also the
existing **drift/skip-hook authoring stance** (harness owns the deterministic scaffolding around
model/AI content) applied to container builds.

---

## 5. Recommended approach

**Parameterized per-language Dockerfile TEMPLATE + a `build_service_image(service, workdir)` builder
that reuses `provision.py`.** NOT hand-written Dockerfiles per service.

- **One template per language** (5 templates), parameterized by: service name, entry file, stub source,
  dep-closure path, run CMD, exposed port. The map in §1 supplies every parameter from the seed +
  `contract.py` (the run CMD is literally `resolve_serve_command` minus the `cd && exec` sandbox wrap).
- **`build_service_image(service, workdir)`** assembles the build context: stages the generated source,
  calls the **existing** offline-dep helpers (`setup_go_stubs`, `.pydeps` install_plan, node closure
  copy, dotnet publish), drops in the language template Dockerfile, then `docker build` with
  `--network=none` (proves hermeticity) producing `r3/<model>/<service>:<tag>`.
- **Offline base-image prep is mandatory:** pre-pull the 5 language base images (golang, python-slim,
  node-alpine, dotnet sdk+runtime, temurin) once with network, then build `--network=none`. Bake the
  dep caches (NuGet, .m2, GOMODCACHE, wheels, node_modules) into the build context / a local registry
  so no build stage reaches the network. This is the container analog of the closures already vendored.
- **Egress denial moves to the network layer:** compose `internal: true` network (or k8s NetworkPolicy
  deny-egress); keep default seccomp/cap-drop/non-root for the untrusted services. Per-service Seatbelt
  is dropped — the container *is* the boundary now.

**Rationale:** the templates + builder reuse ~80% of what already exists; hand-Dockerfiles would
duplicate the offline-dep logic 9× and drift from `provision.py`. A template parameterized off the same
seed/contract that drives the bare-process fleet keeps the two substrates honest about the same inputs.

---

## 6. Reusable vs net-new (the ledger)

**REUSE (already built, just relocate into a build stage):**
- Go stub vendoring + `replace` + `go build` → `setup_go_stubs`, `install_plan("go")`.
- Python gRPC stubs + `.pydeps` wheel closure + Jinja2 → `demo_pb2*.py`, `install_plan("python")`.
- Node full offline closure → `node_runtime/node_modules`, `prepare_node_workdir`.
- C# publish + Grpc.Tools codegen → `publish_dotnet_service` (the compile half).
- Run CMDs for all 5 → `contract.py` `_DEFAULTS` (Java still absent).
- Security posture framing (scripts-disabled, scrubbed env, fail-closed-offline) → `provision.py` header.

**NET-NEW:**
- 5 parameterized Dockerfile templates + `build_service_image(service, workdir)` builder.
- Offline base-image prep + a local image/cache store (the build-context dep caches).
- **C# warm-NuGet-cache baking** (the unsolved half of the C# offline story).
- **Java lane end-to-end** (no provisioning exists — recommend deferring adservice to v2).
- Network-layer egress denial (`internal` network / NetworkPolicy) replacing per-process Seatbelt.
- docker-compose fleet generation (9 services + DNS wiring of `*_SERVICE_ADDR`); kind manifests later.
- Multi-arch handling (dev arm64 vs CI/prod amd64).

---

## 7. Open questions / risks for the compose-fleet prototype

- **OQ-C1 — Offline base-image availability.** Hermeticity requires the 5 base images pre-pulled and
  pinned by digest (upstream Dockerfiles already pin by sha256 — reuse those digests). Risk: a stale or
  missing base image silently re-opens the network. **Must fail closed** like the dep closures do.
- **OQ-C2 — Build-time scale.** 9 images × N models = up to ~9N builds per round. Go/C#/Java
  multi-stage compiles dominate (C# publish + Java gradle are minutes each). Need build caching /
  layer reuse keyed on the harness-owned base+deps layers (which are model-invariant) so only the thin
  source layer rebuilds per model. Without this, a 5-model round is ~45 image builds.
- **OQ-C3 — Image size.** Distroless/scratch (Go), runtime-deps-chiseled (C#), alpine (Node/Python),
  jre-alpine (Java). Self-contained/trimmed C# from upstream is large — prefer framework-dependent.
  Budget per-image size targets; a 9-service fleet × N models can balloon disk.
- **OQ-C4 — arm64 vs amd64.** Dev is **arm64 macOS**; CI/prod may be **amd64**. Dep closures
  (.pydeps wheels, grpcio C-ext, NuGet runtime packs) are arch-specific — a wheel/cache baked on arm64
  won't load on amd64. Decide: build per-target-arch (cache per arch) or pin a single CI arch. The Node
  closure is mostly pure-JS (portable); grpcio and dotnet runtime-deps are the arch-sensitive ones.
- **OQ-C5 — Java in v1?** adservice is the only Java service, a leaf (GetAds) off the canonical journey,
  and the only language with zero offline-build support. **Recommend: v1 = 8 services (Go/Python/Node/C#),
  defer adservice/Java to v2.** The canonical browse→cart→checkout→payment→confirm journey doesn't need ad.
- **OQ-C6 — C# cold-NuGet hermeticity.** The single load-bearing unsolved reuse gap. Needs a warm-cache
  bake-and-snapshot step before the compose prototype can claim full offline.
- **OQ-C7 — compose vs kind parity.** Egress denial is `internal: true` in compose vs `NetworkPolicy`
  in kind; service DNS differs (compose service name vs k8s Service). The `*_SERVICE_ADDR` wiring must
  be substrate-parameterized so the journey driver is identical across both.

---

## 7b. Canonical reference (microservices-demo-latest)

Authoritative upstream: `~/Documents/dev/micro-service-demo/microservices-demo-latest/src/<service>/Dockerfile`.
This is the **digest-pinned, multi-arch** canonical build for each language and is the TEMPLATE the
harness's per-language Dockerfile should mirror (the harness swaps the network-fetch dep steps for
pre-baked offline caches but keeps the *build pattern*). Every upstream Dockerfile uses
`FROM --platform=$BUILDPLATFORM ... AS builder` + `ARG TARGETARCH`/`ARG TARGETOS` cross-compile — so
**multi-arch is the canonical norm**, which directly answers OQ-C4 (build per-target-arch is the
upstream default, not an exotic ask).

| Lang | Canonical Dockerfile | Base (build → runtime), digest-pinned | Authoritative build pattern | Offline-prep hook |
|---|---|---|---|---|
| **Go** | `src/{checkoutservice,frontend,productcatalogservice,shippingservice}/Dockerfile` | `golang:1.25.6-alpine@sha256:98e6cf…` → `gcr.io/distroless/static` | `COPY go.mod go.sum` → `go mod download` → `GOOS/GOARCH CGO_ENABLED=0 go build -ldflags="-s -w" -o /<svc>` | `go mod download` after copying only go.mod/go.sum (cache layer) |
| **Python** | `src/{recommendationservice,emailservice,loadgenerator}/Dockerfile` | `python:3.14.2-alpine@sha256:31da4c…` (`shoppingassistant` uses `-slim`) builder → same base | `COPY requirements.txt` → `pip install -r` (loadgen uses `--prefix=/install`) → `COPY --from=builder /usr/local/lib/python3.14/ …` | wheels installed in builder stage, copied into runtime (no network at run) |
| **Node** | `src/{currencyservice,paymentservice}/Dockerfile` | `node:20.20.0-alpine@sha256:09e2b3…` builder → `alpine:3.23.3@sha256:251091…` + `apk add nodejs` | `COPY package*.json` → `npm install --only=production` → `COPY --from=builder …/node_modules` | `npm install --only=production` in builder; proto loaded at runtime |
| **C#** | `src/cartservice/src/Dockerfile` | `mcr.microsoft.com/dotnet/sdk:10.0.100-noble@sha256:c7445f…` builder → `dotnet/runtime-deps:10.0.0-noble-chiseled@sha256:b857c8…` | `dotnet restore -a $TARGETARCH` → `dotnet publish -p:PublishSingleFile=true --self-contained true -p:PublishTrimmed=true -p:TrimMode=full -c release` → single chiseled `/app/cartservice` binary, `USER 1000` | **`dotnet restore` is the ONLY network step** — bake a warm NuGet cache and it's `--no-restore` |
| **Java** | `src/adservice/Dockerfile` | `eclipse-temurin:24.0.2_12-jdk-noble@sha256:dacac8…` builder → `temurin:25.0.1_8-jre-alpine@sha256:9c65fe…` | `COPY build.gradle gradlew gradle/` → **`./gradlew downloadRepos`** → `COPY . .` → `./gradlew installDist` → run `build/install/hipstershop/bin/AdService` | **`./gradlew downloadRepos` IS a ready-made offline dep-prefetch hook** (a custom gradle task that pulls every repo dep into the local cache up front) |

### De-risking the two hard lanes with canonical evidence

- **C# (cartservice) — LESS risky than §3 ranked it.** The canonical proves the *only* network step is
  `dotnet restore` (everything else — `Grpc.Tools` codegen, trimmed self-contained publish — runs
  offline once the cache is warm). So the C# offline gap collapses to exactly **one** task: warm the
  NuGet cache once (`dotnet restore` with network), snapshot `~/.nuget/packages` into the build context,
  then `dotnet publish` against it. Note upstream **does** use `PublishSingleFile + self-contained +
  PublishTrimmed=full` (heavier than the framework-dependent stance in §3/OQ-C3) — but it lands on a
  *chiseled runtime-deps* image and a single binary, so it is the canonical target; the warm-cache bake
  is the whole job. **Revised read: C# ≈ a quarter-suite, not half** (publish path + codegen are
  upstream-proven; only the cache snapshot is new).
- **Java (adservice) — LESS greenfield than §3 framed it.** Upstream ships **`./gradlew downloadRepos`**,
  a purpose-built dep-prefetch task: run it once online to populate the gradle cache, then `installDist`
  builds fully offline. So Java is NOT "no offline story" — the offline-prefetch hook already exists
  upstream; the harness work is to (a) bake the gradle cache from `downloadRepos`, (b) inject the
  harness-owned `build.gradle`/`gradlew`/`gradle/` wrapper around the generated `.java` (same
  build-files-injection stance as every other language, §4), (c) add a `_java_default` launcher running
  `build/install/hipstershop/bin/AdService`. The FR-P1-SEC-1 "untrusted build script" hazard remains
  (gradle executes `build.gradle`), so the harness should own the build.gradle (not run the model's),
  mirroring the C# "publish a harness-owned csproj" stance. **Revised read: Java ≈ half-to-three-quarters
  of a suite, not a full greenfield lane** — `gradlew installDist` + `downloadRepos` is a known-good
  pattern, not invention. The v2-defer recommendation can stay (adservice is still a leaf off the
  canonical journey), but the *cost* of pulling it into v1 is materially lower than originally scoped.

### Digest-pinning & multi-arch as canonical norms

Every upstream base image is **sha256-digest-pinned** (reuse those exact digests in OQ-C1 — they are
the authoritative pins, e.g. Go `golang:1.25.6-alpine@sha256:98e6cf…`, C# sdk `@sha256:c7445f…`). And
every builder is **multi-arch via `--platform=$BUILDPLATFORM` + `ARG TARGETARCH`** — so for OQ-C4 the
faithful answer is to build per-target-arch (the upstream default) rather than pinning one CI arch;
only the *dep caches* (.pydeps wheels, grpcio C-ext, NuGet runtime-deps, dotnet self-contained runtime
pack) are the arch-sensitive layers that need per-arch baking. Note the upstream pins are **newer**
than §2's reference (`golang:1.21`, generic `python:3.x-slim`) — update the templates to the
microservices-demo-latest digests above.

---

## 8. Rough size/effort read

**Bigger than one behavioral suite, but not by a lot — call it ~1.5–2× a suite, concentrated in 2 lanes.**

- Go / Python / Node containerization ≈ **thin wrappers** over existing closures (~one suite's worth
  total for all three: templates + the builder + base-image prep).
- C# ≈ **~quarter-suite** (canonical §7b proves `dotnet restore` is the only network step → just the
  warm-NuGet bake on top of the upstream-proven trimmed self-contained publish + Grpc.Tools codegen).
- Java ≈ **~half-to-three-quarters of a suite** (canonical §7b shows `./gradlew downloadRepos` is a
  ready offline dep-prefetch hook + `installDist` is the build pattern — bake the gradle cache, inject a
  harness-owned `build.gradle`/wrapper, add a `_java_default` launcher). NOT a full greenfield lane.
  The v2-defer recommendation can still hold (adservice is a leaf off the canonical journey), but the
  cost of pulling it into v1 is materially lower than originally scoped.
- The fleet-compose generation + network-egress denial + multi-arch caching ≈ another suite's worth,
  shared across all languages.

So **v1 (8 services, no Java)** ≈ comparable to building **one-and-a-half behavioral suites**, most of
it reuse-and-relocate. **v1 + Java** pushes it toward **~2×** (not 2.5×) — the canonical-reference
re-read (§7b) downgrades Java from "full greenfield" to "known-good `downloadRepos` + `installDist`
pattern with a cache bake," and C# from "half-suite" to "~quarter-suite (warm-NuGet bake only)." The
compose prototype is feasible on the existing offline assets for 4 of 5 languages; C# needs one
warm-cache bake step and Java needs a gradle-cache bake + harness-owned build.gradle — both now have an
upstream-proven offline pattern to mirror rather than invent.
