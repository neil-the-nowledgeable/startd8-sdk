# Generated-App Health Endpoint — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-15
**Status:** Planned against backend_codegen; ready for CRP / implementation
**Owner:** SDK / backend_codegen
**Motivated by:** deploy-harness finding (b) — StartDate graded `health=pass:liveness-only` because it
exposes no real `/health` route; only FastAPI's framework-served `/openapi.json` answered.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 after planning against the real `backend_codegen`
> pipeline. 6 corrections — past the 30% bar, so v0.1 was appropriately premature.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Readiness can live at `/health` OR `/health/ready` | The deploy harness probes **bare `/health`** (`deploy_harness/server.py` `_PROBES`); a `prefix="/health"` router with only `/ready` 404s on `/health` → stays `liveness-only` | FR-1/FR-9: readiness MUST be `GET /health` exactly |
| "non-2xx on failure" suffices | The obvious renderer returns **200** with an error body; the harness would read that as healthy | FR-1/FR-8: readiness returns **HTTP 503** on DB failure (explicit) |
| Health may need mode-specific rendering | `db.py` `engine`/`get_session()` already honor `DATABASE_URL` (installed=SQLite, deployed=Postgres) | FR-7: `health.py` is **mode-invariant** — one schema-only artifact, not deployed-only like `settings.py` |
| Emission is purely additive (FR-5/6) | Mounting the router edits `render_main` → the **`fastapi-main` artifact bytes change** | FR-5/6: golden trees + runtime smoke + main-drift tests update; existing apps drift until regenerated |
| Owned-kind registration may need `provider.py` + special-casing | Schema-only kind → default drift path; `provider.py` unchanged; just `CANONICAL_LAYOUT` + `drift._renderers()` | FR-4 simpler than written |
| Readiness depth unspecified | `session.exec(text("SELECT 1"))` via the existing session API is sufficient + decoupled | OQ-3 → `SELECT 1` only |

**Resolved open questions:**
- **OQ-1 → SDK-generated.** The pipeline supports it cleanly (owned artifact); confirmed, not a one-off StartDate edit.
- **OQ-2 → Default-on.** Accept the one-time `fastapi-main` + new-file drift (existing apps regenerate); a flag is over-engineering for a $0 applicational-completion artifact.
- **OQ-3 → `SELECT 1` only.** No table-existence coupling.
- **OQ-4 → Both, but readiness at bare `/health`.** `GET /health` = readiness (the harness's probe); `GET /health/live` = liveness. NOT readiness-under-`/health/ready`-only.
- **OQ-5 → Normative contract:** `GET /health` → `200 {"status":"ok"}` ready / `503 {"status":"degraded","checks":{"db":"down"}}` not-ready; `GET /health/live` → `200 {"status":"alive"}`.

---

## 1. Problem Statement

Generated all-Python apps (`generate backend`) have **no application-defined health endpoint**. The
deploy harness probes `/health` → `/openapi.json` → `/`; with no `/health`, only `/openapi.json`
answers, so the harness can only confirm **liveness** (the framework process is up), not **readiness**
(the app's DB layer actually works). This understates real apps in the benchmark and gives operators
no readiness signal.

A health endpoint is **applicational completion** of a generated app (bucket 1 — deterministic, $0
LLM), not content. It belongs in the deterministic cascade, emitted for every app.

| Component | Current state | Gap |
|-----------|---------------|-----|
| Liveness | Implicit (port binds, `/openapi.json` serves) | — |
| Readiness | None | No check that the DB/session layer is functional |
| Harness signal | `pass:liveness-only` | Can't reach `pass:app-health` |
| Ops signal | None | No endpoint for a load balancer / container healthcheck |

---

## 2. Goals & Non-Goals

**Goals**
- Every generated app exposes a deterministic `/health` endpoint (bucket 1, $0 LLM).
- Distinguish **liveness** (process up) from **readiness** (DB reachable).
- Make the harness's health rung grade `pass:app-health` for a healthy app.
- Drift-safe and idempotent like every other `backend_codegen` artifact.

**Non-Goals (v1)**
- Deep dependency health (Redis, external APIs, downstream services).
- Metrics/observability endpoints (`/metrics`) — separate concern.
- Auth on the health endpoint.
- Authoring real status content.

---

## 3. Requirements

### Endpoint shape
- **FR-1** Every generated app exposes **`GET /health`** (the *readiness* endpoint, at the bare path —
  this is exactly what the deploy harness probes) returning `200 {"status":"ok"}` when ready, and
  **`503 {"status":"degraded","checks":{"db":"down"}}`** when the readiness check fails. The 503 is
  required: a 200-with-error-body would read as healthy to the harness and to load balancers.
- **FR-2** Provide a distinct **liveness** endpoint **`GET /health/live`** → always `200
  {"status":"alive"}` if the process serves. (Readiness is the bare `GET /health`, NOT
  `/health/ready`-only — a `prefix="/health"` router that omits the bare path 404s on `/health`.)
- **FR-3** The **readiness** check verifies the DB/session layer with a trivial `SELECT 1` round-trip
  via the existing `get_session`/`engine` (no table-existence coupling), not merely that the process
  is up. A DB failure → 503 naming the failing check.

### Generation & drift
- **FR-4** `/health` is emitted by `backend_codegen` as a **deterministic, schema-only owned artifact**
  `app/health.py`: a `CANONICAL_LAYOUT["fastapi-health"]` entry + a `drift._renderers()` entry, with a
  `# startd8-artifact: fastapi-health` + `schema-sha256` header so `generate backend --check`
  re-renders and byte-matches it ($0 skip). **No `provider.py` change** and no AI/pages/forms/settings
  special-casing — it uses the default drift path.
- **FR-5** The router is **mounted additively in `render_main`** (`app.include_router(health_router)`
  after `web_router`). This **changes the `fastapi-main` artifact bytes** — it is additive at the app
  level but not byte-neutral for `main.py`.
- **FR-6** Because FR-5 changes `fastapi-main`, the **same change updates** the affected SDK fixtures:
  the `fastapi-main` golden tree(s), `test_runtime_smoke.py`, and any main-drift assertion — plus adds
  the new `app/health.py` golden and the generated health test. Existing generated apps show `main.py`
  + new-file drift until regenerated (the accepted cost of default-on, OQ-2).

### Deployment-mode awareness
- **FR-7** The readiness DB check uses the app's configured engine (`installed` → SQLite;
  `deployed` → Postgres via `DATABASE_URL`), so `/health` reflects the mode-appropriate datastore.
- **FR-8** In `deployed` mode where the DB must pre-exist, a missing/unreachable DB yields a non-2xx
  readiness response (fail-closed), not a 200.

### Harness alignment
- **FR-9** With FR-1 satisfied, the deploy harness's health rung grades **`pass:app-health`** (a real
  readiness 200), not `pass:liveness-only`. (No harness change required — it already probes `/health`
  first; this is the producing side.)

### Backfill
- **FR-10** Document that **existing apps (incl. StartDate) acquire `/health` by regenerating** the
  backend; provide the one-line regeneration path. Until regenerated they remain `liveness-only`.

---

## 4. Non-Requirements

- Does NOT add `/metrics`, tracing, or auth.
- Does NOT health-check external/downstream dependencies in v1.
- Does NOT change the deploy harness (it already prefers `/health`).
- Does NOT hand-edit StartDate; StartDate gets `/health` via regeneration (FR-10).

---

## 5. Open Questions

All five v0.1 open questions were resolved during planning — see §0 (Resolved open questions). None
block implementation. Remaining decisions are settled: SDK-generated, default-on, `SELECT 1`,
bare-`/health` readiness + `/health/live` liveness, and the normative 200/503 status contract.

---

*v0.2 — Post-planning self-reflective update. 6 requirements corrected (FR-1,2,3,4,5,6), 5 open
questions resolved, 0 deferred. Key corrections: readiness lives at bare `GET /health` (harness probe);
failure is HTTP 503; `health.py` is mode-invariant; mounting changes the `fastapi-main` artifact.
Paired with HEALTH_ENDPOINT_PLAN.md v1.0.*
