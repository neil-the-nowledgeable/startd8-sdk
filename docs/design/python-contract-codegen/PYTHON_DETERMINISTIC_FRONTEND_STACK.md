# Python deterministic frontend stack

**Status:** reference (shipped stack)  
**Audience:** anyone assembling or extending the all-Python server-rendered UI  
**Related:** [`PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md`](./PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md),
[`DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md`](../deterministic-frontend/DETERMINISTIC_CONTRACT_CODEGEN_CHARTER.md),
[`SCAFFOLD_GENERATOR_REQUIREMENTS.md`](./SCAFFOLD_GENERATOR_REQUIREMENTS.md)

---

## What this is

The SDK’s **Python deterministic frontend** is not a React/SPA generator. It is a **$0, no-LLM**
projection of a `.prisma` contract into a **server-rendered modular monolith**:

| Layer | Role |
|-------|------|
| **Contract** | `.prisma` (neutral IDL) |
| **API + persistence** | Pydantic v2 + SQLModel + FastAPI JSON CRUD |
| **UI** | Jinja2 templates + HTMX partials, served by FastAPI HTML routes |
| **Presentation** | Plain CSS (base inline + optional Presentation Polish stylesheet) |
| **Composite views** | `views.yaml` → dashboard / board / workspace / … (same Jinja+HTMX surface) |

This is **bucket 1 — applicational completion**: structural skeleton (forms, lists, CRUD, views), not
end-user brand copy. The LLM path is reserved for integration (bucket 3), not for inventing forms.

> **Sibling, not this stack:** `frontend_codegen/` (`startd8 generate frontend`) emits
> **Prisma → Zod/TS** (`value-model.ts`) for TypeScript islands. That is the original deterministic
> frontend *kernel* proof; the **all-Python UI** lives in `backend_codegen/` + polish + views.

---

## Libraries and frameworks (generated app)

Fixed by the FastAPI + SQLModel + HTMX target. Declared in scaffold’s `pyproject.toml`
(`scaffold_codegen/renderers.py`) and the backend’s generated `requirements.txt`.

### Runtime (required)

| Package | Role in the UI/app |
|---------|-------------------|
| **[FastAPI](https://fastapi.tiangolo.com/)** | App spine: JSON routers + HTML/`/ui/*` routes (`web.py`) |
| **[SQLModel](https://sqlmodel.tiangolo.com/)** | ORM tables = contract projection; session CRUD |
| **[Pydantic](https://docs.pydantic.dev/) ≥2** | API/validation DTOs (`XCreate` / `XRead` / `XUpdate`) |
| **[Jinja2](https://jinja.palletsprojects.com/)** | Server-rendered HTML templates (`fastapi.templating.Jinja2Templates`) |
| **[uvicorn](https://www.uvicorn.org/)** `[standard]` | ASGI server |
| **[python-multipart](https://github.com/Kludex/python-multipart)** | Form body parsing (required for HTMX/browser POSTs) |
| **SQLite** (via SQLModel/SQLAlchemy URL) | Default persistence (`sqlite:///…`); WAL + busy_timeout for HTMX bursts |

### Browser / client (CDN, not a Python dep)

| Library | Version / how | Role |
|---------|---------------|------|
| **[HTMX](https://htmx.org/)** | `https://unpkg.com/htmx.org@2.0.3` in `base.html` | Partial swaps, validate-on-blur, delete/confirm without a SPA |

No React, Next.js, Vue, Alpine, Tailwind, or build-step bundler in this path. The UI is **HTML over
the wire** with HTMX attributes (`hx-post`, `hx-trigger`, `hx-target`, `hx-swap`).

### Optional / adjacent

| Package | When |
|---------|------|
| **anthropic** | Scaffold runtime dep for AI edge patterns (BackgroundTasks + polling), not the CRUD UI itself |
| **OpenTelemetry FastAPI instrumentation** | When `app.yaml` enables telemetry |
| **alembic**, **mypy**, **pytest**, **httpx** | Dev extras from scaffold |

### Presentation (Tier 1 polish — CSS only)

`startd8 polish apply` does **not** add a CSS framework. It writes a deterministic stylesheet from
design tokens + a curated theme (`professional` | `editorial` | `minimal`), mounts `/static/css/app.css`,
and drops optional Jinja partials under `templates/theme/` — **zero edits to owned template bodies**.
Target: WCAG 2.2 AA contrast on critical token pairs.

---

## Cascade commands ($0)

```bash
startd8 generate backend   # Prisma → models + CRUD + HTMX UI (+ optional pages/nav/forms)
startd8 generate scaffold  # app.yaml → pyproject, logging, Alembic, Dockerfile
startd8 generate views     # views.yaml → composite Jinja views on the same stack
startd8 polish apply       # theme CSS + static mount hooks
startd8 polish check       # drift of polish artifacts
startd8 wireframe          # read-only preview of what the cascade will build
```

Related: `startd8 generate frontend` = Zod/TS only; `startd8 polish themes` lists themes.

---

## What the UI generator emits

Owned by `backend_codegen/htmx_generator.py` (and siblings for pages/nav/onboarding). Typical tree:

```
app/
  main.py              # FastAPI app; mounts JSON routers + web_router; optional static
  web.py               # HTML routes: /ui/<entity>/… + /validate
  routers.py           # JSON CRUD
  db.py                # SQLite engine + session
  models/ …            # Pydantic + SQLModel projections
  templates/
    base.html          # HTMX script + layout + polish/nav include seams
    _nav.html          # default top nav (optional)
    _field_error.html  # validate-on-blur error slot fragment
    <entity>/
      list.html
      _row.html
      detail.html
      form.html
      _confirm.html    # if entity has confirmed Boolean
      created.html     # if forms: on_create: confirmation
```

### Locked HTMX vocabulary (CRUD + inline validation)

Per entity (with a single-column PK):

| Surface | Behavior |
|---------|----------|
| **List** | Rows; delete via `hx-post` + `outerHTML` swap; optional confirm toggle |
| **Detail** | Read view; confirm block when applicable |
| **Create / edit form** | Field widgets from schema; plain browser POST → **303 See Other** (PRG) |
| **Validate** | `hx-post` + `hx-trigger="blur changed"` → field-level error fragment |
| **Delete** | Partial swap + `hx-confirm` |

**Field → widget map:** enum → `<select>`; Boolean → checkbox; Int/BigInt / Float/Decimal → number;
DateTime → `datetime-local`; else → text. Entities without a single-column PK get list + create only.

### Post-submit destinations

Default: new record’s detail with `?created=1` flash. Override via `views.yaml` top-level `forms:`
(`on_create: detail | list | form | confirmation`).

---

## Inputs that shape the frontend

| Input | Consumed by | Effect on UI |
|--------|-------------|--------------|
| `schema.prisma` | `generate backend` | Entities, fields, widgets, routes |
| `views.yaml` | `generate views` + forms section for backend | Composite views; form redirect policy |
| `app.yaml` | `generate scaffold` | Package name, deps, port, DB path, telemetry |
| `pages` / pages authoring | backend pages generators | Marketing/shell pages beyond entity CRUD |
| `human_inputs.yaml` | backend forms | Fields withheld from generic HTMX writes |
| Display / filter / form-prose manifests | backend | Labels, list filters, form copy hints |

All owned files carry provenance headers (`# startd8-artifact: …`, `schema-sha256:` / Jinja
`{# … #}` wrappers) so the prime-contractor **skip-hook** can mark them `$0.00 GENERATED` when
in sync (`--check` drift).

---

## SDK modules (ownership map)

| Package | Entry point / CLI | Frontend-relevant output |
|---------|-------------------|-------------------------|
| `backend_codegen/` | `pydantic-sqlmodel` · `generate backend` | FastAPI + Jinja/HTMX UI + models |
| `scaffold_codegen/` | `scaffold` · `generate scaffold` | `pyproject.toml` deps + run plumbing |
| `view_codegen/` | `composite-view` · `generate views` | Multi-entity Jinja views (dashboard, board, workspace, …) |
| `presentation_polish/` | `presentation-polish` · `polish *` | CSS theme + static mount |
| `frontend_codegen/` | `prisma-zod` · `generate frontend` | Zod/TS only (not the Python HTML UI) |

Providers register under `startd8.contractors.deterministic_providers`.

---

## Architecture sketch

```text
                    schema.prisma
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
   Pydantic DTOs    SQLModel tables   field → widget map
          │               │               │
          └─────── FastAPI JSON CRUD ─────┘
                          │
                   FastAPI /ui/* (web.py)
                          │
              Jinja2 templates + HTMX 2.0.3
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
     base CSS (inline)      polish → /static/css/app.css
              │                       │
              └──── browser HTML ────┘
```

---

## Explicit non-goals (this path)

- SPA frameworks (React/Next/Vue/Svelte) as the primary generated UI  
- CSS frameworks (Tailwind, Bootstrap) as required deps  
- Hand-authored component trees inventing fields not in the contract  
- Real end-user / company content (bucket 4) — placeholders only where needed to prove the app  
- Tier-2 LLM “bespoke design” (deferred; polish is Tier-1 CSS only)

---

## Quick verify

```bash
# After generate backend (+ deps installed):
uvicorn <package>.main:app --reload
# JSON:  /… entity routers
# HTML:  /ui/<entity>/ …
```

Unit runtime coverage: `tests/unit/backend_codegen/test_runtime_smoke.py` (skips if app deps absent).

---

## See also

- Ideal target architecture: `docs/design/IDEAL_TARGET_ARCHITECTURE.md`  
- Form submit / confirm / empty-state / FK picker: sibling REQ/PLAN docs in this folder  
- Presentation polish package docstring: `src/startd8/presentation_polish/__init__.py`
