# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: fastapi-main
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

# Secrets hydration (FR-GEN-1..3): populate os.environ from the configured backend
# (e.g. Doppler, via ~/.startd8/config.json) BEFORE any import that reads env. The db
# module reads DATABASE_URL at import time, so this runs before that import below.
# Fully guarded: a no-op when startd8 isn't installed or the backend is 'local', and
# fail-open if the backend is unreachable — the app runs identically either way.
try:  # optional managed-secrets hydration (startd8.secrets); no-op for the 'local' backend
    from startd8.secrets import hydrate as _hydrate_secrets
    _hydrate_secrets()
except Exception:
    pass

from .db import init_db
from .health import health_router
from .routers import all_routers
from .web import web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="StartDate", lifespan=lifespan)

for _router in all_routers:
    app.include_router(_router)
app.include_router(web_router)  # server-rendered HTMX UI at /ui/*
app.include_router(health_router)  # /health (readiness) + /health/live (liveness)

try:  # optional presentation-polish static mount (startd8 polish); no-op until polish runs
    from .static_setup import mount_static
except ModuleNotFoundError:
    mount_static = None
if mount_static is not None:
    mount_static(app)  # serves /static/* (e.g. the polished stylesheet) when present

try:  # optional OWNED routers — the regen-safe composition seam (D2).
    from .user_routers import user_routers  # project-authored list; never generated
except ModuleNotFoundError:
    user_routers = []
for _user_router in user_routers:
    app.include_router(_user_router)  # owned routers/views survive regenerate

try:  # optional content-pages layer (generate backend --pages)
    from .pages import pages_router
except ModuleNotFoundError:
    pages_router = None
if pages_router is not None:
    app.include_router(pages_router)  # home / and content slugs

try:  # optional page-authoring UI (generate backend --pages-authoring)
    from .pages_admin import pages_admin_router
except ModuleNotFoundError:
    pages_admin_router = None
if pages_admin_router is not None:
    app.include_router(pages_admin_router)  # /ui/pages authoring screens

try:  # optional AI layer (generate backend --ai-passes); /ai/* one POST per pass (F-9)
    from .ai.routes import ai_router
except ModuleNotFoundError:
    ai_router = None
if ai_router is not None:
    app.include_router(ai_router)  # AI passes reachable at /ai/* via app.main
try:  # optional AI-pass UI triggers (ai_passes.yaml `trigger:`); detail-page buttons (FR-AIT)
    from .ai.ui import ai_ui_router
except ModuleNotFoundError:
    ai_ui_router = None
if ai_ui_router is not None:
    app.include_router(ai_ui_router)  # POST /ui/<entity>/{id}/run-<pass>
try:  # optional step-state flows (views.yaml `flows:`); /flow/<name>/* (FR-WZ-5)
    from .flows import flow_routers
except ModuleNotFoundError:
    flow_routers = []
for _flow_router in flow_routers:
    app.include_router(_flow_router)  # start/resume/advance/back
try:  # optional bulk child-field editors (views.yaml `editors:`); <route> per editor (FR-ED-8)
    from .editors import editor_routers
except ModuleNotFoundError:
    editor_routers = []
for _editor_router in editor_routers:
    app.include_router(_editor_router)  # GET grouped editor + POST bulk save
try:  # optional bulk-import surface (imports.yaml `surface: true`); GET/POST /import (FR-IMP-6)
    from .import_surface import import_surface_router
except ModuleNotFoundError:
    import_surface_router = None
if import_surface_router is not None:
    app.include_router(import_surface_router)  # paste/upload import screen
