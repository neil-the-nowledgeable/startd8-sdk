# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: fastapi-web
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from .db import get_session
from .tables import PlaceOrderSession


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
web_router = APIRouter()


def _coerce(kind: str, raw: str):
    """Coerce a raw form string to the field's Python kind (Pydantic does the rest on validate)."""
    if raw == "" or raw is None:
        return None
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "checkbox":
        return raw not in ("", "off", "false", "0")
    if kind == "text-list":
        return [p.strip() for p in raw.split(",") if p.strip()]
    return raw


def _field_error(kind: str, required: bool, raw: str) -> str:
    """Deterministic single-field validation message ("" = valid)."""
    if required and (raw is None or str(raw).strip() == ""):
        return "This field is required."
    if raw in (None, ""):
        return ""
    if kind == "int":
        try:
            int(raw)
        except ValueError:
            return "Must be a whole number."
    if kind == "float":
        try:
            float(raw)
        except ValueError:
            return "Must be a number."
    return ""


# --- PlaceOrderSession ---
_placeordersession_rules = {"userId": ("text", True), "email": ("text", True)}


@web_router.get("/ui/placeordersession", response_class=HTMLResponse)
def list_placeordersession(request: Request, session: Session = Depends(get_session)):
    items = list(session.exec(select(PlaceOrderSession)).all())
    ctx = {"items": items, "created": request.query_params.get("created"),
           "filters": dict(request.query_params)}
    return templates.TemplateResponse(
        request, "placeordersession/list.html", ctx
    )


@web_router.get("/ui/placeordersession/new", response_class=HTMLResponse)
def new_placeordersession(request: Request):
    prefill = {k: v for k, v in request.query_params.items() if k in _placeordersession_rules}
    ctx = {"item": None, "prefill": prefill, "created": request.query_params.get("created")}
    return templates.TemplateResponse(
        request, "placeordersession/form.html", ctx
    )


@web_router.post("/ui/placeordersession/validate", response_class=HTMLResponse)
async def validate_placeordersession(request: Request):
    form = await request.form()
    message = ''
    for key, value in form.items():
        if key in _placeordersession_rules:
            kind, required = _placeordersession_rules[key]
            message = _field_error(kind, required, value)
            break
    return templates.TemplateResponse(
        request, "_field_error.html", {"message": message}
    )


@web_router.post("/ui/placeordersession", response_class=HTMLResponse)
async def create_placeordersession(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    data = {k: _coerce(_placeordersession_rules[k][0], form.get(k))
            for k in _placeordersession_rules if form.get(k) not in (None, '')}
    obj = PlaceOrderSession(**data)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return RedirectResponse(f"/ui/placeordersession/{obj.id}?created=1", status_code=303)


@web_router.get("/ui/placeordersession/{id}", response_class=HTMLResponse)
def detail_placeordersession(id: str, request: Request, session: Session = Depends(get_session)):
    item = session.get(PlaceOrderSession, id)
    if item is None:
        raise HTTPException(status_code=404, detail="PlaceOrderSession not found")
    ctx = {"item": item, "created": request.query_params.get("created"),
           "updated": request.query_params.get("updated")}
    return templates.TemplateResponse(
        request, "placeordersession/detail.html", ctx
    )


@web_router.get("/ui/placeordersession/{id}/edit", response_class=HTMLResponse)
def edit_placeordersession(id: str, request: Request, session: Session = Depends(get_session)):
    item = session.get(PlaceOrderSession, id)
    if item is None:
        raise HTTPException(status_code=404, detail="PlaceOrderSession not found")
    return templates.TemplateResponse(
        request, "placeordersession/form.html", {"item": item}
    )


@web_router.post("/ui/placeordersession/{id}", response_class=HTMLResponse)
async def update_placeordersession(id: str, request: Request, session: Session = Depends(get_session)):
    obj = session.get(PlaceOrderSession, id)
    if obj is None:
        raise HTTPException(status_code=404, detail="PlaceOrderSession not found")
    form = await request.form()
    for k in _placeordersession_rules:
        if form.get(k) not in (None, ''):
            setattr(obj, k, _coerce(_placeordersession_rules[k][0], form.get(k)))
    session.add(obj)
    session.commit()
    return RedirectResponse(f"/ui/placeordersession/{id}?updated=1", status_code=303)


@web_router.post("/ui/placeordersession/{id}/delete", response_class=HTMLResponse)
def delete_placeordersession(id: str, session: Session = Depends(get_session)):
    obj = session.get(PlaceOrderSession, id)
    if obj is not None:
        session.delete(obj)
        session.commit()
    return HTMLResponse(
        '<tr><td colspan="5">'
        '<p class="flash">✓ PlaceOrderSession deleted.</p></td></tr>'
    )
