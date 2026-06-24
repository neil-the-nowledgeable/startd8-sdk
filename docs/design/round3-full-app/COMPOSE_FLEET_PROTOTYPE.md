# Round 3 — docker-compose FLEET Substrate PROTOTYPE

**Date:** 2026-06-24
**Status:** **PROTOTYPE — implemented + LIVE-VALIDATED on macOS Docker 2026-06-24** (Docker Desktop
4.73, arm64): a 2-service Online Boutique fleet, recommendation→productcatalog over **service-DNS
gRPC**, scored **coverage 1.0**, with **egress denied at the network layer** + clean teardown. Not
the full 9-service fleet (that is the scoped containerization implementation — see
`CONTAINERIZATION_SCOPING.md`).
**Location:** `docs/design/round3-full-app/compose-prototype/`
**Driver:** `compose-prototype/drive_fleet.py` · **gated test:** `tests/integration/test_compose_fleet_prototype.py`
**Parents:**
- `CONTAINMENT_SPIKE.md` (verdict B — Seatbelt loopback fleet; Docker deferred to a later substrate)
- `NETNS_SUBSTRATE.md` (the Linux netns substrate this prototype is the **macOS-native Docker analog** of)
- `CONTAINERIZATION_SCOPING.md` (the per-language image build layer this prototype is the existence-proof for)

---

## 1. What this proves (the substrate claim)

This is the **docker-compose analog of the netns smoke**. Where `NETNS_SUBSTRATE.md` proved a fresh
shared Linux netns gives *gRPC-loopback + egress-deny + hermeticity simultaneously* (which Seatbelt
could not), this prototype proves the **container substrate** gives the same two properties on a
plain macOS Docker host — and additionally the **faithful production-like topology** (each service in
its own image/container, peers reached by **service-DNS**, not a shared loopback):

1. **service-DNS over real gRPC** — `recommendationservice` dials `productcatalogservice:8080` **by
   name** over the compose network. A real container-to-container gRPC `ListProducts` call, not an
   in-process mock and not host loopback.
2. **egress DENIED at the network layer** — the fleet's backend network is a compose
   `internal: true` network: Docker creates **no gateway / no route out**, so a container on it
   **cannot reach any external host**. Containment is *structural* (no egress filter to mis-scope),
   exactly like the netns "no veth → no route out" — and exactly what the macOS Seatbelt either/or
   could not give alongside working gRPC.
3. **a driver scores the fleet end-to-end** — the existing SDK `run_recommendation_suite` scores the
   live fleet over the wire; coverage 1.0 requires the inter-service call to have actually happened
   and produced correct behavior.

This simultaneously delivers **faithful production-like networking** (service-DNS, real gRPC, one
container per service) **and containment** (network-layer egress-deny) — the combination the macOS
Seatbelt process-sandbox structurally cannot.

## 2. Topology

```
                          ┌─────────── edge (bridge) ───────────┐
   host:127.0.0.1:18080 ──┤  recommendationservice  (INGRESS)   │
   (SDK scoring client)   └──────────────────┬──────────────────┘
                                             │ service-DNS gRPC
                          ┌──────────────────┴──────────────────┐
                          │   fleet  (internal: true — NO egress)│
                          │  recommendationservice ──► productcatalogservice:8080
                          │                         (pure BACKEND, fleet-only)
                          └──────────────────────────────────────┘
```

| Service | Lang | Networks | Reachability | Role |
|---|---|---|---|---|
| `productcatalogservice` | Go | `fleet` only | peers only (service-DNS); **no host, no egress** | pure backend — the egress-deny probe target |
| `recommendationservice` | Python | `fleet` + `edge` | host (published `127.0.0.1:18080`) + dials productcatalog over `fleet` | ingress (the OB-frontend analogue) |

- **`fleet`** = `internal: true`. Both services join it; this is where the inter-service gRPC call
  flows and where egress is impossible. `productcatalog` is on `fleet` **only** → strictest case.
- **`edge`** = a normal bridge carrying **only** host↔recommendation ingress (the published port).
  It does **not** connect productcatalog, so the productcatalog dial is **forced** through the
  internal network. This mirrors real OB: the frontend is reachable; backends stay internal.
- **service-DNS env injection:** recommendation gets
  `PRODUCT_CATALOG_SERVICE_ADDR=productcatalogservice:8080` — the **exact `*_SERVICE_ADDR`
  convention the startup contracts declare** (`contract.py`), now resolved by compose DNS instead of
  an in-process stub's ephemeral loopback port.

> **Why recommendation needs `edge`:** a service on an `internal: true` network *cannot publish a
> port to the host* (no route in either direction). To let the host-side SDK scoring client reach the
> SUT — exactly as `run_recommendation_suite` connects to `127.0.0.1:<port>` — recommendation also
> joins a normal bridge. productcatalog stays internal-only, so the egress-deny claim is proven on
> the strict backend. (Full hardening would also egress-deny `edge`; see §6.)

## 3. How the Dockerfiles get the OB stubs in (reuse of `provision.py` patterns)

The images replicate exactly what the behavioral harness does at prepare time — assembled by
`prepare_build_context.sh`, which copies from the SDK's own behavioral sources (no hand-maintained
stub duplicates):

- **productcatalogservice (Go)** — mirrors `provision.setup_go_stubs` + `install_plan("go")`:
  - The prep script copies the vendored protoc stubs
    (`behavioral/go_stubs/hipstershop/demo.pb.go`, `demo_grpc.pb.go`) into `_stubs/` and **synthesizes
    the localmod `go.mod`** (`module github.com/GoogleCloudPlatform/microservices-demo/hipstershop`)
    — byte-for-byte the same vendoring `setup_go_stubs` performs.
  - The service `go.mod` carries `require … hipstershop v0.0.0` + `replace … => ./_stubs` (the
    upstream module restructured and no longer ships `hipstershop`, so we resolve it locally — the
    same reason `setup_go_stubs` exists).
  - The Dockerfile runs `go mod tidy && go build` (the `install_plan("go")` command), producing a
    static `/app/server`. **grpc v1.81.1 requires Go ≥ 1.25** → builder image `golang:1.25-alpine`.
  - `products.json` is the **harness-owned ground-truth catalog** written from
    `recommendation_ground_truth()` (the recommendation oracle's 5-product universe), so the catalog
    the suite expects and the catalog the container serves are the same fixed source.
- **recommendationservice (Python)** — mirrors `install_plan("python")` + the demo_pb2 co-location:
  - `pip install grpcio protobuf`, then **co-locate `demo_pb2.py` / `demo_pb2_grpc.py`** next to
    `server.py` (the OB Python convention — module-not-package — exactly what the test stager does).
  - The server is the `recommendation_reference` fixture **unchanged in behavior**: it reads
    `PRODUCT_CATALOG_SERVICE_ADDR`, dials productcatalog's `ListProducts`, returns ids from the
    catalog excluding the request inputs.

## 4. The faithful inter-service call-counter

The recommendation suite asserts `catalog_dialed = stub_calls[PRODUCT_CATALOG_SERVICE_ADDR] > 0` — in
the in-process harness that counter is `RecommendationDepHarness._CallCounter`. With a **real
container** peer there is no in-process counter, so the prototype reconstructs the same signal
**faithfully from the wire**: the Go server logs a `DIAL ListProducts` line per call, and
`drive_fleet.py` counts those lines in `docker compose logs productcatalogservice` (delta across the
suite run) and feeds the count to `run_recommendation_suite` as `stub_calls`. A service that returned
hardcoded ids without dialing would show **zero** dials and fail the counter cases — the same
discrimination the in-process counter gives.

## 5. LIVE validation result (macOS Docker, 2026-06-24)

`python3 drive_fleet.py` (and the gated pytest) produced:

```
[fleet] recommendation suite coverage = 1.000
[fleet] productcatalog real dials during suite = 2
    - rec_excludes_input:    PASS  got=['1YMWWN1N4O','L9ECAV7KIM','2ZYFJ3GM2N']
    - rec_empty_input:       PASS  got=['OLJCESPC7Z','66VCHSJNUP','1YMWWN1N4O','L9ECAV7KIM']
    - rec_subset_of_catalog: PASS  all_ids_in_catalog=True
[fleet] egress to 1.1.1.1:443 DENIED (internal network contained it)
[fleet] SUBSTRATE PROVEN: service-DNS gRPC coverage 1.0 + egress denied + clean teardown.
```

- **(a) coverage 1.0 over the real inter-service gRPC call** — recommendation excluded its inputs and
  returned only catalog ids, which it could only know by dialing productcatalog by service-DNS;
  productcatalog logged **2 real dials** during the suite (one per `ListRecommendations`).
- **(b) egress denied** — `nc -w5 -z 1.1.1.1 443` from inside the pure-backend productcatalog
  container returned `EGRESS_DENIED`. Genuineness double-checked: the same probe from a default
  (non-internal) container returns `EGRESS_OPEN`, so the deny is real network-layer containment, not
  a tool quirk.
- **(c) clean teardown** — `docker compose down -v --remove-orphans` always runs (finally); verified
  no leftover containers/networks.
- **Ran on macOS Docker:** yes — Docker Desktop 4.73 (linux/arm64 engine). Containers have a real
  Linux network stack inside the Docker VM, so this works natively on the macOS dev host (unlike the
  Seatbelt gRPC-loopback gap, and without needing a Linux box for netns).

**One build fix during validation:** grpc-go 1.81.1 needs Go ≥ 1.25; the builder base was bumped from
`golang:1.23-alpine` to `golang:1.25-alpine`. No other blockers.

## 6. How this maps to the full 9-service fleet

The prototype is the existence-proof for `CONTAINERIZATION_SCOPING.md`'s `build_service_image`
layer. The mapping is mechanical:

- **each service → one image/container.** The 2 Dockerfiles here become the per-language Dockerfile
  TEMPLATE the scoping doc specifies; `build_service_image(service, workdir)` stages the generated
  source + provisioned stubs (reusing `setup_go_stubs` / demo_pb2 co-location / `publish_dotnet_service`)
  exactly as `prepare_build_context.sh` does here by hand for 2.
- **`*_SERVICE_ADDR` deps from the startup contracts → compose service-DNS.** Every OB dependency env
  the contracts declare (checkout's 6, recommendation's 1, …) becomes a `SERVICE: name:port` env on
  the internal network — the same substitution shown here, fanned out. Checkout's 6 real peers light
  up the same way recommendation's 1 does.
- **internal network egress-deny scales unchanged** — all 9 backends join one `internal: true`
  `fleet` network; an ingress/loadgenerator service joins `edge` for scoring. The containment claim is
  identical at 9 services.
- **the driver generalizes** — `run_recommendation_suite` is one of the existing per-service suites
  (catalog, charge, currency, checkout, cart, …); the fleet driver runs each suite against its
  service container, and the `DIAL`-log call-counter pattern generalizes to any dependency edge.

## 7. Honest limitations + what the containerization implementation still needs

- **Prototype = 2 services, not 9.** Recommendation→productcatalog is the minimal 1-dependency edge.
  The full fleet (Go 3 / Python 2 / Node 2 / C# 1 / Java 1) is the scoped implementation, not this.
- **Build used the network** (pulled base images + go/pip deps). The substrate claim is about
  **RUNTIME** networking + egress-deny; **offline/`--network=none` build hermeticity** is the next
  step (`CONTAINERIZATION_SCOPING.md` §"offline build"). Node already has the vendored `node_runtime/`
  closure; Go/Python need pre-warmed module/wheel caches baked into the build context.
- **arm64 only validated.** Ran on Docker Desktop's linux/arm64 engine; multi-arch / amd64 CI images
  are untested here.
- **The hard per-language lanes are unbuilt:**
  - **C# (cartservice)** — `publish_dotnet_service` exists but `dotnet publish`'s **NuGet restore
    needs network on a cold cache**; a hermetic image must bake a warm `~/.nuget`.
  - **Java (adservice)** — **net-new, no provisioning exists at all** (`install_plan` returns None,
    no `_java_default` contract). Needs a secured `javac`-over-vendored-jars lane (NOT `gradle`,
    which executes untrusted build scripts) + a warm `~/.m2`.
- **`edge` is not egress-denied.** Recommendation (the ingress) can still reach the internet via
  `edge`. The deny is proven on the strict backend (productcatalog, `fleet`-only). Full hardening
  would egress-deny `edge` too (e.g. an egress-firewall sidecar or a published-port-only ingress that
  itself has no default route) — a v2 concern.

## 8. Re-run

```bash
cd docs/design/round3-full-app/compose-prototype
make drive            # prepare contexts -> build -> up -> score (coverage 1.0) -> egress-deny -> teardown
# or: python3 drive_fleet.py
# or, as a gated pytest (skips unless docker + STARTD8_RUN_INTEGRATION=1):
STARTD8_RUN_INTEGRATION=1 pytest tests/integration/test_compose_fleet_prototype.py -q
```

Generated build-context artifacts (`_stubs/`, `demo_pb2*.py`, `products.json`) are gitignored and
re-assembled from SDK sources by `prepare_build_context.sh` on every run.
```
