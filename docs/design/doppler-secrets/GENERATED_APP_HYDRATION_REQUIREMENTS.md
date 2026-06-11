# Generated-App Secrets Hydration (default for deterministic generation) — Requirements

**Version:** 0.2 (Post-planning — self-reflective; planning folded in)
**Date:** 2026-06-11
**Status:** Draft → implementing. StartDate (`strtd8/strtd8`) is the reference template.

---

## 0. Planning Insights (Self-Reflective Update)

> Grounded by reading the actual emitter (`backend_codegen/crud_generator.py:render_main`) and the
> StartDate app, before writing FRs.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Wire hydration via a per-app launch shim (`app_run.py`) + change the launch command | `app/main.py` is **SDK-generated** (`fastapi-main` artifact); the shim belongs *in the generator*, not per-app | **No shim, no launch change.** Emit the preamble inside `render_main`; Dockerfile CMD stays `app.main:app`. The StartDate `app_run.py` becomes redundant. |
| Hydrate in the FastAPI `lifespan`/startup hook | `app/db.py` reads `DATABASE_URL` at **import** time, and `main.py` does `from .db import init_db` at module load | Hydration MUST run **before** `from .db import init_db` — a lifespan hook is too late for import-time env reads. → preamble at the very top of `main.py` (FR-GEN-3). |
| Generated apps may not have the SDK installed | StartDate already imports the SDK at runtime (`resolve_agent_spec`), but a pure-CRUD app might not | The preamble must be **fully guarded** (try/except around import *and* call) so a no-SDK / no-backend app runs byte-for-byte the same (FR-GEN-2/6). |
| Big test/golden churn | `test_backend_codegen` asserts **substrings** (additive-safe); `drift.py` re-renders `render_main` live (no stored golden); the NR-7 pytest guard forces `backend=local` in tests | Low blast radius: existing assertions still pass; generated-app smoke tests call `hydrate()` as a **no-op**; only StartDate needs regen. |

**Net:** the clean home is the generator, not the app. The earlier `app_run.py` shim was a correct
stopgap; this requirement makes it unnecessary.

## 1. Problem Statement

`startd8 generate backend` emits a deterministic all-Python app, but the generated app has **no way to
source secrets from a managed backend**: it reads `os.environ` directly, so credentials/config must be
present in the process env by some external means. The SDK now ships a Doppler-capable secrets backend
(`startd8.secrets.hydrate()`) — generated apps should pick it up **by default**, with no per-app wiring,
so an app generated from a Prisma schema "just works" against the operator's configured backend.

| Component | Current | Gap |
|-----------|---------|-----|
| Generated `main.py` | reads no secrets backend | values must be hand-injected into env; no Doppler |
| Wiring | manual (`app_run.py` shim per app) | not regen-safe at the app level; needs an SDK home |
| Import-time reads (`DATABASE_URL`) | from raw env / default | not sourced from the managed backend |

## 2. Requirements

- **FR-GEN-1 — Emit a hydration preamble.** `render_main` emits a secrets-hydration preamble at the
  **top** of `app/main.py`, before any app import that reads env.
- **FR-GEN-2 — Fully guarded / no-op-safe.** The preamble wraps both the import and the call in
  `try/except` so an app without the SDK installed, or with the default `local` backend, imports and
  runs **byte-for-byte identically at runtime** (hydrate is a no-op / fail-open).
- **FR-GEN-3 — Placement before `from .db import init_db`.** Hydration must precede the `db` import,
  because `db.py` reads `DATABASE_URL` at import time. A lifespan/startup hook is too late.
- **FR-GEN-4 — Default-on, unconditional.** Every generated app gets the preamble (no flag required) —
  the guard makes it universally safe. (Opt-out manifest field is a deliberate non-requirement, NR-1.)
- **FR-GEN-5 — Deterministic & idempotent.** The preamble is static text; `generate backend --check`
  reports `in_sync` after regeneration; drift stays self-consistent (live re-render, no golden file).
- **FR-GEN-6 — Preserve the standalone-app property.** The SDK import stays optional (`ImportError`
  → no-op), so an app shipped without `startd8` still runs — only the *managed-backend* feature is lost.
- **FR-GEN-7 — Dockerfile/scaffold unchanged.** The container CMD stays `uvicorn app.main:app`; the
  preamble makes that path hydrate. No `scaffold_codegen` change.
- **FR-GEN-8 — StartDate reference.** Regenerate StartDate, remove the interim `app_run.py` shim, and
  confirm `ANTHROPIC_API_KEY` / `DATABASE_URL` / `COST_BUDGET_USD` resolve from Doppler `startd8/dev`
  via the regenerated `app.main`.

## 3. Non-Requirements

- **NR-1** No `app.yaml` opt-out flag in v1 — the guarded default is safe; add a manifest toggle only
  if a real need appears.
- **NR-2** No change to `scaffold_codegen` (Dockerfile, pyproject) or to `settings_renderer.py`
  (deployment-mode). The preamble runs *before* `settings.py` reads, so it composes cleanly.
- **NR-3** Not forcing `startd8` as a hard runtime dependency of generated apps (FR-GEN-6).
- **NR-4** No change to the backend-selection mechanism — generated apps read the same global
  `~/.startd8/config.json` / env the SDK does.

## 4. Open Questions

- **OQ-1 — Resolved:** preamble vs shim → preamble in `render_main` (§0).
- **OQ-2 — Resolved:** placement → before `from .db import init_db` (FR-GEN-3).
- **OQ-3 — Deferred (NR-1):** manifest opt-out. Revisit if a no-hydration app is ever needed.

---

*v0.2 — planning folded in. Reference template: StartDate. Paired implementation lands in
`backend_codegen/crud_generator.py` (render_main) + a `test_backend_codegen` assertion.*
