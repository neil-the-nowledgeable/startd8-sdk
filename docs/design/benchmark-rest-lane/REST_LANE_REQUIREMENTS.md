# Track 2 REST/HTTP Behavioral Lane — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-18
**Status:** Draft (planning-corrected; pre-implementation)
**Plan:** `REST_LANE_PLAN.md`
**Scope:** Phase 2 of the Liferay benchmark work — add a REST/HTTP loopback behavioral lane to the
Track 2 harness so seeds can be Liferay-native REST (not only gRPC), enable a REST pricing seed, and
lay groundwork for the multi-service target.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass made **contact with the actual harness** and falsified the framing this whole
> phase started from — *including the user's own characterization* that the REST lane is "meatier,
> touches the harness." It barely touches the harness. The Track 2 harness was built
> protocol-agnostic, and an HTTP readiness probe already ships elsewhere in the SDK. Net: scope
> collapsed, ~6 requirements narrowed, several quick wins surfaced (§2.1), and the value/cost ratio
> inverted from "significant harness work" to "~150 additive lines unlocking the dominant real-world
> protocol."

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1: extend the harness to host HTTP | `run_service_sandboxed` is **100% protocol-agnostic** (raw TCP readiness, pass-through `client(port)`, pure process orchestration) — zero changes | FR-1 narrowed to "wire a readiness *mode*"; no sandbox change |
| FR-2: build an HTTP readiness probe | The shipped **deploy harness** already has a stdlib `_probe(url)→ok/http/down` + probe-order — lift it | FR-2 → **reuse**, not build; new FR-11 (shared primitive) |
| FR-3: build an HTTP suite-client framework | `httpx` already a dep; `SuiteResult`/`_SUITES` already protocol-neutral | FR-3 narrowed to "write one suite file"; no framework |
| FR-4: REST dependency provisioning | REST **skips proto provisioning**; a stdlib REST server needs **zero** vendored deps; only fix = make grpc deps protocol-aware | FR-4 narrowed + the real fix named |
| FR-5: seed schema needs new REST fields | `StartupContract.readiness` **already exists** (default "tcp"), just unused | FR-5 narrowed to "wire it + add `health_path`" |
| (latent) `readiness:"tcp"` is honored | It is **read but never consumed** — harness always TCP-probes | New correctness win folded into FR-1/FR-5 |
| (implicit) one-off REST hack | Agnosticism makes this a **protocol-dispatch generalization** (GraphQL etc. ~free later) | New FR-10 (protocol-pluggable) — flexibility/value |

**Resolved open questions:**
- **OQ-1 → No harness change.** `run_service_sandboxed`/`sandbox.py` is protocol-agnostic (raw TCP probe + pass-through client).
- **OQ-2 → Yes, reuse it.** `deploy_harness/server.py` has a stdlib HTTP probe; extract to a shared `readiness.py` (FR-11).
- **OQ-3 → Prose endpoint contract in `requirements_text`** for the pilot (OpenAPI-derived), mirroring how the gRPC seed embeds the proto; full OpenAPI-file provisioning deferred.
- **OQ-4 → Stdlib, zero deps** for the pilot REST server; the lane must not *require* a framework.
- **OQ-5 → Minimal.** Add `health_path` to `StartupContract` and honor the existing `readiness` field; backward-compatible.

---

## 1. Problem Statement

The Track 2 behavioral harness scores a model-generated service by launching it under the sandbox
and running an SDK-authored ground-truth suite against it over loopback. Today every suite is
**gRPC** (`grpc.insecure_channel` + proto stubs). Liferay Commerce — and most real-world services —
are **REST/HTTP**, so a faithful "Liferay-native" seed can't be expressed in the current harness.
Phase 1 shipped a gRPC pricing seed by *translating* Liferay's REST contract into a proto; Phase 2
removes that translation by giving the harness a native REST lane.

| Component | Current State | Gap |
|-----------|--------------|-----|
| Service launch + sandbox | gRPC services only (assumed) | Needs HTTP-server support |
| Readiness | TCP port probe | HTTP servers need a health-endpoint probe |
| Suite client | gRPC stubs | Needs an HTTP client to hit endpoints + assert JSON |
| Provisioning | grpc/proto deps | Needs REST deps |
| Seed contract | gRPC/proto seed | Needs a way to declare REST |

## 2. Requirements

**FR-1 — Host HTTP services (readiness mode only).** The harness must host a model-generated HTTP/REST
service under the sandbox alongside gRPC. *Planning-corrected:* `run_service_sandboxed` is already
protocol-agnostic, so the only change is selecting an HTTP **readiness mode** (FR-2) and honoring the
seed's declared readiness — which today is read but never consumed (a latent gap this closes). No
sandbox-launch or teardown change.

**FR-2 — HTTP readiness via the shared probe.** Readiness for a REST server is an HTTP health probe
(poll `health_path`, default `/health`, for 2xx) with a TCP-connected fallback, degrading honestly on
timeout like the rest of the harness. *Planning-corrected:* this is **reuse**, not new code — the
deploy harness already ships a stdlib probe (`deploy_harness/server.py`); see FR-11.

**FR-3 — REST ground-truth suite.** A REST suite hits endpoints with request bodies and asserts status
codes + response JSON, returning the **same** `SuiteResult`/`.coverage` contract and registered in the
**same** `_SUITES` registry as gRPC suites. *Planning-corrected:* no framework — `httpx` is already a
core dependency and `SuiteResult` is already protocol-neutral; this is one new suite file.

**FR-4 — Provisioning: skip proto, protocol-aware deps.** REST cells **skip proto provisioning
entirely** and must not install gRPC deps. Make `provision.py` protocol-aware so a REST Python cell
installs `httpx` (or nothing for a stdlib server) instead of `grpcio`/`protobuf`. A minimal stdlib REST
server (Python `http.server`, Node `http`) requires **zero** vendored deps.

**FR-5 — REST seed contract (minimal schema delta).** A seed declares REST via the existing
`StartupContract.readiness:"http"` plus an additive `health_path`; the endpoint contract is embedded in
`requirements_text` (OpenAPI-derived prose, mirroring how the gRPC seed embeds its proto). Backward-
compatible: absent fields default to the gRPC/TCP behavior.

**FR-6 — Liferay-native REST pricing seed.** Re-express the pricing capability as REST endpoints
(near-direct translation from Liferay's headless-commerce OpenAPI — *more faithful and easier to ground-
truth than the Phase-1 gRPC translation*) with an SDK-authored REST ground-truth suite (the same G1–G7
pricing semantics).

**FR-7 — Scoring parity (no change).** REST functional coverage folds into the composite identically
(`scoring.py` consumes a float — protocol-blind). No scoring change.

**FR-8 — Backward compatibility.** Existing gRPC seeds/cells remain byte-identical; the lane is purely
additive (guarded by a regression test).

**FR-9 — Multi-service groundwork (doc-only here).** Document the small delta to host >1 REST service +
an integration suite (a second port + readiness), given the harness already hosts one process. No
multi-service build in this phase.

**FR-10 — Protocol-pluggable, not REST-specific.** Frame the lane as a **protocol dispatch** (readiness
mode + provisioning + suite-client convention keyed off the seed), with REST as the first non-gRPC
protocol. Because the harness is agnostic, GraphQL / other HTTP-shaped protocols slot in later for
near-zero work — the seam must be a small enum/field, not a REST-hardcoded branch.

**FR-11 — Shared readiness primitive (single source of truth).** Extract the deploy harness's HTTP probe
into a shared `benchmark_matrix/readiness.py` (`wait_ready(port, mode, *, health_path, timeout)`) that
**both** the deploy harness and the behavioral lane import — avoiding two divergent HTTP probes. Keep the
deploy harness's existing probe-order/timing and tests green.

### 2.1 Quick Wins / Low-Hanging Fruit (surfaced by planning)

These were not evident before contact with the code; each is high-value and cheap:

- **QW-1 — Free readiness.** The HTTP probe already exists (deploy harness, stdlib-only) → lift, don't build.
- **QW-2 — Free client.** `httpx` is already a core dep → REST suites add zero dependencies.
- **QW-3 — Close a latent bug.** `StartupContract.readiness` is declared but ignored; wiring it makes the
  contract real and is a correctness fix independent of REST.
- **QW-4 — Simpler than gRPC.** REST seeds skip proto provisioning + (stdlib) need no vendored runtime —
  *less* setup than the gRPC pricing seed required.
- **QW-5 — Disproportionate value.** ~150 additive lines unlock the **dominant real-world protocol** and
  every Liferay-native seed, and (FR-10) generalize to future protocols for free.
- **QW-6 — Reuse hardens both.** Sharing one readiness module (FR-11) removes a future-divergence risk
  between the deploy harness and the behavioral lane.

## 3. Non-Requirements

- **Not** GraphQL / WebSocket / gRPC-web — REST/HTTP first.
- **Not** stateful sessions / auth flows — stateless suites like the gRPC ones.
- **Not** replacing or deprecating the gRPC lane.
- **Not** the full multi-service target — groundwork only (FR-9).

## 4. Open Questions

All five v0.1 open questions were resolved by planning (see §0). Remaining items are
implementation-time calibrations, not blockers:

- **CQ-1** REST contract fidelity — the OpenAPI-derived prose in `requirements_text` must pin the OPEN
  choices REST leaves loose (status codes, JSON envelope, error shape) precisely enough for deterministic
  ground truth; confirm on the actual pricing contract (relates to the bias-audit's OPEN-item analysis).
- **CQ-2** Pilot REST-server language/shape — pin stdlib (zero-dep) for the reference server; revisit if a
  framework (FastAPI) is wanted for realism.

---

*v0.2 — Post-planning self-reflective update. The planning pass falsified the founding premise (the
harness is already protocol-agnostic): **6 requirements narrowed** (FR-1–FR-5, FR-7 → no/low change),
**2 added** (FR-10 protocol-pluggable, FR-11 shared readiness primitive), **6 quick wins surfaced**
(§2.1), **1 latent bug found** (`readiness` declared-but-ignored), and all 5 open questions resolved.
The loop earned its keep: it converted a "significant harness rewrite" into "~150 additive lines + one
reuse," and reframed the value as unlocking the dominant real-world protocol for the whole benchmark.*
