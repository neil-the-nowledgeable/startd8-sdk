# Generated-App Health Endpoint — Implementation Plan

**Version:** 1.0 (paired with Requirements v0.2)
**Date:** 2026-06-15
**Status:** Planned — pre-implementation

---

## 0. Planning Discoveries (feed §0 of the requirements)

| v0.1 assumed | Planning revealed | Impact |
|--------------|-------------------|--------|
| Readiness can live at `/health` or `/health/ready` (FR-1/2) | The **deploy harness probes bare `/health`** (`server.py` `_PROBES`); a `prefix="/health"` router with only `/ready` 404s on `/health` → stays `liveness-only` | Readiness MUST be `GET /health` exactly; FR-9 only works then |
| Non-2xx on failure (FR-1/8) | The obvious renderer returns **200** with an error body (no `status_code`); harness would read false-healthy | Readiness must return **HTTP 503** on DB failure (explicit `Response`/`HTTPException`) |
| Health may need mode-specific rendering (FR-7) | `db.py` `engine`/`get_session()` already read `DATABASE_URL` (installed=SQLite, deployed=Postgres) | `health.py` is **mode-invariant** — ONE schema-only artifact for both modes (not deployed-only like settings.py) |
| Emission is additive, won't touch golden trees (FR-5/6) | Mounting the router edits `render_main` → the **`fastapi-main` artifact bytes change** | Not purely additive: `fastapi-main` golden trees + runtime smoke + main-drift tests update; existing apps drift until regenerated |
| Owned-kind registration may need provider.py + special-casing | It's a **schema-only** kind → default drift path; `provider.py` unchanged; just `CANONICAL_LAYOUT` + `drift._renderers()` | FR-4 is simpler than written — no AI/pages/forms/settings special set |
| Readiness depth unspecified (OQ-3) | `session.exec(text("SELECT 1"))` via existing session API is sufficient + decoupled | OQ-3 → `SELECT 1` only (no table-existence coupling) |

These exceed the 30% bar → v0.1 was appropriately premature; corrections captured at doc cost.

## 1. Files touched (grounded in `settings_renderer.py` / `derived.render_export` as templates)

- **NEW `backend_codegen/health_renderer.py`** — `render_health(schema_text, source_file="prisma/schema.prisma") -> str`.
  Header via `_headers.header_standard(source_file, schema_sha256(schema_text), "fastapi-health")`; body is a
  deterministic, mode-invariant FastAPI router. Routes:
  - `GET /health` → readiness: `SELECT 1` via `get_session`; `200 {"status":"ok"}` on success,
    `503 {"status":"degraded","checks":{"db":"down"}}` on failure (fail-closed, FR-8).
  - `GET /health/live` → liveness: always `200 {"status":"alive"}` (FR-2).
- **`crud_generator.py`**
  - `CANONICAL_LAYOUT["fastapi-health"] = "app/health.py"` (the owned-kind registration).
  - `render_main`: additively `from .health import health_router` + `app.include_router(health_router)`
    after the `web_router` mount. (This changes the `fastapi-main` artifact — see §3.)
- **`assembler.py`** — emit `(CANONICAL_LAYOUT["fastapi-health"], render_health(schema_text, source_file))`
  right after `fastapi-main` in `render_backend`'s ordered `out` list.
- **`drift.py`** — add `"fastapi-health": lambda s, sf, e: render_health(s, sf)` to `_renderers()` (lazy import).
  Schema-only kind → falls through the default re-render+byte-compare path; no kind-set changes.
- **`test_emitter.py`** — `render_health_tests(schema_text, source_file) -> str` → `tests/test_health.py`
  (kind `python-tests-health`): TestClient asserts `GET /health` → 200 `{"status":"ok"}` and
  `GET /health/live` → 200. Register its kind in `drift._renderers()` + emit in `assembler.py`.
- **`__init__.py`** — export `render_health` if the package re-exports renderers (match existing convention).
- **`provider.py`** — **no change** (kind auto-recognized once in `_renderers()`).

## 2. Per-requirement steps

- **FR-1/FR-2 (endpoints)** — `render_health` emits `GET /health` (readiness) + `GET /health/live`
  (liveness). Readiness uses the existing `get_session` dependency; on `Exception` returns a 503 via
  `fastapi.responses.JSONResponse(status_code=503, ...)` (or `HTTPException(503)`).
- **FR-3 (readiness = DB round-trip)** — `session.exec(text("SELECT 1"))` (`from sqlalchemy import text`);
  trivial, no schema/table coupling (OQ-3).
- **FR-4 (owned/drift-safe)** — `CANONICAL_LAYOUT` entry + `_renderers()` entry; header carries
  `# startd8-artifact: fastapi-health` + `schema-sha256`; deterministic → `--check` re-renders & byte-matches.
- **FR-5 (mount)** — additive `include_router` in `render_main`; **accept** the `fastapi-main` byte change.
- **FR-6 (don't break tests)** — update the `fastapi-main` golden tree(s), `test_runtime_smoke.py`, and any
  main-drift assertion to include the health mount; add the new health golden + health test.
- **FR-7 (mode-aware)** — satisfied for free: readiness uses the app's `engine`/`DATABASE_URL`; ONE artifact.
- **FR-8 (fail-closed)** — DB unreachable → 503 (above). Verified by a test that points `DATABASE_URL` at an
  unreachable DB and asserts 503.
- **FR-9 (harness alignment)** — once `GET /health` returns a real 200, the deploy harness grades
  `pass:app-health`. No harness change. Add an SDK test (or note) confirming the probe path matches.
- **FR-10 (backfill)** — doc: existing apps run `startd8 generate backend` to acquire `/health`;
  StartDate regenerates.

## 3. The `fastapi-main` drift cost (default-on)

Mounting `/health` by default changes `render_main` output, so **every** generated app's `app/main.py`
shows drift on `--check` until regenerated, and the SDK's own `fastapi-main` golden/runtime tests must be
updated in the same change. This is the accepted cost of default-on (OQ-2). Alternative considered:
gate behind an `app.yaml` flag to avoid forcing drift — rejected as over-engineering for a $0 applicational-
completion artifact; one regen is cheap and `/health` should be universal.

## 4. Sequencing

- **M0** — `health_renderer.py` + `CANONICAL_LAYOUT` + `assembler` emit + `drift._renderers()` entry; unit
  test the rendered bytes + drift in-sync. (No main.py change yet → no golden churn; health.py present but
  unmounted — still importable.)
- **M1** — wire the `render_main` mount; update `fastapi-main` goldens + `test_runtime_smoke` + main-drift
  tests; assert `GET /health` 200 and `/health/live` 200 live (TestClient).
- **M2** — `render_health_tests` generated test + its kind; fail-closed (503) test with an unreachable DB.
- **M3** — regenerate StartDate (`startd8 generate backend`) to acquire `/health`; re-run the deploy harness
  on it → confirm `health=pass:app-health` (the end-to-end proof tying back to the motivating finding).

## 5. Risks

- **`session.exec(text(...))` API drift** across SQLModel versions — fall back to
  `session.connection().exec_driver_sql("SELECT 1")` if `.exec(text())` isn't supported.
- **Golden-tree churn** — M1 touches `fastapi-main` goldens; keep M0 (no main change) separate so the
  health renderer lands green before the main.py churn.
- **503 vs 200 semantics** — must be 503 for the harness signal to be meaningful; covered by the fail-closed test.

## 6. Test plan

- Unit: `render_health` byte-stable + header/sha; drift `owned_file_in_sync` True for a freshly rendered
  `app/health.py`; `render_health_tests` shape.
- Runtime (importorskip fastapi/sqlmodel): generate a backend → TestClient → `GET /health`==200,
  `/health/live`==200; point `DATABASE_URL` at an unreachable DB → `GET /health`==503.
- End-to-end (M3): regenerate StartDate, `startd8 deploy local … --editable …` → `health=pass:app-health`.

## 7. Traceability

FR-1..10 each map to a step in §2; §0 resolves OQ-1..5. No open questions block implementation.
