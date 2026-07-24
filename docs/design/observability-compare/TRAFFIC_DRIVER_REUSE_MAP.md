# Reuse Map — a traffic driver for compare-live span-metrics standup (don't rebuild)

**Status:** reference (grounded 2026-07-24, 4-scope search: SDK, ContextCore, wider dev, InsightFinder demo)
**For:** `SUBJECT_COVERAGE_REQUIREMENTS.md` — the review's **High finding**: Inc-2 (span-metrics standup)
degrades to always-`unknown` because the standup drives **no traffic**, and span-metrics emit **no series
until the subject handles a request** (verified: `live_standup.py:229-278` boots + scrapes, never drives).
**Thesis:** the traffic driver needs **~zero new code**. The SDK already ships three classes of request
driver; the wider dev folder ships realistic locust loadgenerators; and the standup's own FR-2 compose can
carry a loadgen as **one more container**. **Cite/orchestrate; do not build a new load engine.**

Unqualified `file:line` are in `~/Documents/dev/startd8-sdk`.

---

## 1. In-SDK drivers — Tier-0 (zero new deps, already in-repo)

| Driver (`file:line`) | Drives | Transport | Input seam | Fit for compare-live |
|---|---|---|---|---|
| **`benchmark_matrix/fleet/frontend_gate.py:49` `run_journey_http(client)`** | the 5-step OB journey (browse→setCurrency→addToCart→viewCart→checkout), cookie-threaded, one session | **HTTP** via injected `httpx.Client` | `httpx.Client(base_url=<ingress>)` | **Top pick for an OB-shaped HTTP subject.** Point the client at the standup's published ingress; call in a short loop to materialize span-metrics. `httpx` is already a dep. |
| **`benchmark_matrix/fleet/adapter_b.py:227` `run_journey(addr_map)`** | same 5-step journey over direct gRPC | **gRPC** | `addr_map: {service: "host:port"}` | **Top pick for a gRPC subject/fleet.** Feed it the stood-up service DNS/ports. Standalone (no docker coupling). |
| **`deploy_harness/smoke.py:70` `run_smoke(base_url)`** | **schema-driven** round-trip: `GET /openapi.json` → synthesize a POST body → `POST` a CRUD resource → `GET` back | **HTTP** | `base_url` only | **Top pick for an ARBITRARY subject** (the common compare-live case — Mastodon, a traces-only app — is NOT online boutique). Discovers the app's own routes; no journey hardcoding. Loop it to sustain traffic. |
| behavioral suites — `behavioral/charge_suite.py:72` `run_charge_suite(port)` (+ cart/checkout/catalog/…) | per-service deterministic RPC sequences | gRPC/HTTP | `client(port)` | niche — single-service exercise; use when the subject is one known service, not a journey |

**Why these are the answer:** the SDK already drives real requests two ways — an **OB-journey** driver
(`run_journey_http`/`run_journey`) and a **generic OpenAPI** driver (`run_smoke`). Between them they cover
"the subject is the benchmark corpus" and "the subject is an arbitrary app." Neither needs a new engine.

## 2. The elegant integration — the loadgen is just another compose service

`SUBJECT_COVERAGE_REQUIREMENTS.md` **FR-2 already generates a multi-container compose** (fleet net +
service-DNS + ingress). A traffic generator is **one more service in that compose**, pointed at the
subject's ingress by env — no new standup code. Two shapes:

- **(b) Host-side driver — recommended for v1.** After `_await_scrape` releases, call `run_journey_http(httpx.Client(base_url=ingress))` (OB subject) or `run_smoke(ingress)` (generic subject) from the host in a
  bounded loop, then re-gate on span-metric series appearing. **Zero new containers, zero new deps.**
- **(a) In-compose loadgen sidecar — the realistic-load upgrade.** Add a locust loadgenerator container to
  the FR-2 compose (see §3), `FRONTEND_ADDR=<subject-ingress>`. Fits the compose mechanism exactly;
  produces weighted sustained load. Cost: a locust image + a `locustfile.py` (lift, don't write).

## 3. Wider-dev drivers — Tier-1 (lift a container for realistic sustained load)

| Source | What | Portability |
|---|---|---|
| **`~/Documents/dev/online-boutique-python-artisan/src/loadgenerator/locustfile.py`** (161 lines, robust; also `online-boutique-demo/`, `micro-service-demo/…`) | locust `FastHttpUser`, weighted OB task mix (browse 10 / cart 2 / checkout 1 …), Faker checkout data, Dockerfile `ENTRYPOINT locust --host=$FRONTEND_ADDR --headless` | **Excellent** — env-driven host; drop-in compose sidecar |
| **`~/Documents/Jobs/.../Insight-Finder/demo/opentelemetry-demo/src/loadgenerator/locustfile.py`** | the **CNCF OTel-Demo** loadgen — locust + `locust_plugins` PlaywrightUser + **OTel-instrumented** (emits its own OTLP traces) | Heavy (playwright/locust_plugins deps) but **OTel-native** and pairs with the exact demo whose `otelcol-config-extras.yml` seeded `collector_enrichment` |
| **`~/Documents/dev/telemetery-bouncer/telemetrybouncer/lab/generate_load.sh`** | trivial shell loop hitting 4 endpoints at N req/s (`./generate_load.sh 60 10`) | Medium — demo endpoints, but the pattern is 5 lines |
| **`~/Documents/dev/OSS/mastodon/scripts/phase6-b1-traffic-gen-runbook.md`** | **the proven pattern** — POST a status ~10–20× → triggers `PostStatusService` fan-out → **populates `traces_spanmetrics_*` histograms in Mimir** | The reference *technique* for exactly this need, proven on a real multi-container app |

The Mastodon runbook is the ground truth that this works: **"POST N times → span-metric histograms
materialize."** That is precisely Inc-2's warm-up step.

---

## 4. What does NOT fit (honest boundary)

- **ContextCore `scripts/load_tasks_to_tempo.py`** (OTLP span emitter) — injects **synthetic spans straight
  into Tempo**, bypassing the subject. Wrong layer: it does not exercise the subject, so the subject's own
  span-metrics never fire. Useful to *pre-populate a backend*, not to *drive a subject*. (ContextCore has
  **no** sustained load generator — confirmed.)
- **OB journey drivers are OB-specific** — `run_journey_http`/`run_journey` hardcode the 5-step boutique
  flow. For a non-OB subject use `run_smoke` (generic) or a lifted locustfile, not the journey.
- **Full locust** adds `locust`/`gevent` (and playwright for the OTel-demo variant) deps. Fine as a
  **container sidecar** (isolated), a bad idea as an in-process host dep. Prefer §2(b) for v1.
- **`run_smoke` writes** (it POSTs a CRUD resource) — fine for a throwaway standup subject; do not aim it at
  a stateful shared backend.

## 5. Recommendation → fold into SUBJECT_COVERAGE (resolves the review's High finding)

Add one FR to `SUBJECT_COVERAGE_REQUIREMENTS.md`:

> **FR-8 Warm-up traffic (Inc-2 enabler).** Before the span-metric readiness gate, drive bounded traffic
> at the subject's ingress so spans materialize. **v1 reuses an existing driver, adds no engine:**
> `run_journey_http` (OB/HTTP) · `run_journey` (gRPC) · `run_smoke` (generic OpenAPI), selected by subject
> shape; loop until series settle or timeout→`unknown`. **Realistic-load upgrade:** a locust loadgen
> **sidecar in the FR-2 compose** (`FRONTEND_ADDR=<ingress>`), lifted from `online-boutique-*/loadgenerator`.

Net: Inc-2's missing piece is **selection + a bounded loop around drivers that already exist**, plus an
optional compose sidecar that rides the multi-container mechanism the spec already builds. New engine: none.

## 6. Reference Audit
| Symbol / path | Verified |
|---|---|
| `run_journey_http(client: httpx.Client, …)` `frontend_gate.py:49` | ✓ |
| `run_journey(addr_map: dict[str,str], …)` `adapter_b.py:227` | ✓ |
| `run_smoke(...)` `deploy_harness/smoke.py:70` (`GET /openapi.json` :76) | ✓ |
| `stand_up_subject_and_prometheus` drives no traffic `live_standup.py:229-278` | ✓ |
| `collector_config` / `:8889` exporter `runtime_fidelity.py:82` | ✓ |
| OB loadgenerators `online-boutique-python-artisan/src/loadgenerator/locustfile.py` (+2 copies) | ✓ |
| OTel-Demo loadgen `Insight-Finder/demo/opentelemetry-demo/src/loadgenerator/locustfile.py` | ✓ |
| Mastodon span-metrics traffic runbook `OSS/mastodon/scripts/phase6-b1-traffic-gen-runbook.md` | ✓ |
| ContextCore has no sustained load generator (`load_tasks_to_tempo.py` = span injector) | ✓ |
