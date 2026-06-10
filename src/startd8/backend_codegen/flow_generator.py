"""Wizard step-state primitive generation (P0-1) — flow routers + shell templates.

A flow is a multi-step state machine over a **draft entity**: start → resume → advance/back, with the
current step persisted on a declared column. The SDK generates the navigation/state plumbing; per-step
**content** is app-owned (a tolerant `{% include … ignore missing %}` seam). ``on_finish`` is a
tolerant owned-fn hook. See WIZARD_STEP_STATE_REQUIREMENTS.md (FR-WZ-1..5).
"""

from __future__ import annotations

from typing import List, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import parse_prisma_schema
from ._headers import header_forms
from .crud_generator import _pk_field
from .flows_manifest import FlowSpec, parse_flows


def _validate_flow(schema, flow: FlowSpec) -> None:
    model = schema.model(flow.draft_entity)
    if model is None:
        raise ValueError(f"flow {flow.name!r}: unknown draft_entity {flow.draft_entity!r}")
    if model.field(flow.step_field) is None:
        raise ValueError(
            f"flow {flow.name!r}: step_field {flow.step_field!r} is not a column on {flow.draft_entity}"
        )


def render_flow_router(schema_text: str, views_text: str, flow: FlowSpec) -> str:
    """``app/flows/<name>.py`` — the start/resume/advance/back router (FR-WZ-2/4)."""
    schema = parse_prisma_schema(schema_text)
    _validate_flow(schema, flow)
    header = header_forms(
        "prisma/schema.prisma", schema_sha256(schema_text), schema_sha256(views_text), "fastapi-flow"
    )
    entity = flow.draft_entity
    e = entity.lower()
    pk = _pk_field(schema, entity)
    pkname = pk.name if pk is not None else "id"
    sf = flow.step_field
    n = flow.name

    on_finish_import = (
        f"try:  # tolerant on_finish hook (owned fn; no-op if absent) — FR-WZ-4\n"
        f"    from app.flows.finishers import {flow.on_finish} as _on_finish\n"
        f"except Exception:  # noqa: BLE001\n"
        f"    _on_finish = None\n\n"
        if flow.on_finish else "_on_finish = None\n\n"
    )
    finish_call = (
        "        if _on_finish is not None:\n"
        "            _on_finish(item, session)\n"
    )
    body = (
        "from __future__ import annotations\n\n"
        "import logging\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Depends, HTTPException, Request\n"
        "from fastapi.responses import HTMLResponse, RedirectResponse\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlmodel import Session\n\n"
        "from app.db import get_session\n"
        f"from app.tables import {entity}\n\n"
        "logger = logging.getLogger(__name__)\n"
        'templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))\n'
        f"_STEPS = {list(flow.steps)!r}\n\n"
        + on_finish_import
        + f'flow_{n}_router = APIRouter(prefix="/flow/{n}", tags=["flow:{n}"])\n\n\n'
        f'@flow_{n}_router.post("/start")\n'
        f"def start_{n}(session: Session = Depends(get_session)):\n"
        f'    """Create a draft at the first step and open it (FR-WZ-2)."""\n'
        f"    item = {entity}(**{{{sf!r}: _STEPS[0]}})\n"
        f"    session.add(item)\n    session.commit()\n    session.refresh(item)\n"
        f'    return RedirectResponse(f"/flow/{n}/{{item.{pkname}}}", status_code=303)\n\n\n'
        f'@flow_{n}_router.get("/{{draft_id}}", response_class=HTMLResponse)\n'
        f"def show_{n}(draft_id: str, request: Request, session: Session = Depends(get_session)):\n"
        f'    """Render the current step (resume = open the draft at its persisted step)."""\n'
        f"    item = session.get({entity}, draft_id)\n"
        f"    if item is None:\n"
        f'        raise HTTPException(status_code=404, detail="{entity} not found")\n'
        f"    return templates.TemplateResponse(\n"
        f'        request, "flows/{n}/shell.html", {{"item": item, "steps": _STEPS}}\n'
        f"    )\n\n\n"
        f'@flow_{n}_router.post("/{{draft_id}}/advance")\n'
        f"def advance_{n}(draft_id: str, session: Session = Depends(get_session)):\n"
        f"    item = session.get({entity}, draft_id)\n"
        f"    if item is None:\n"
        f'        raise HTTPException(status_code=404, detail="{entity} not found")\n'
        f"    cur = getattr(item, {sf!r})\n"
        f"    i = _STEPS.index(cur) if cur in _STEPS else 0\n"
        f"    if i >= len(_STEPS) - 1:  # past the last step → finish\n"
        + finish_call
        + f'        return RedirectResponse(f"/ui/{e}/{{draft_id}}", status_code=303)\n'
        f"    setattr(item, {sf!r}, _STEPS[i + 1])\n"
        f"    session.add(item)\n    session.commit()\n"
        f'    return RedirectResponse(f"/flow/{n}/{{draft_id}}", status_code=303)\n\n\n'
        f'@flow_{n}_router.post("/{{draft_id}}/back")\n'
        f"def back_{n}(draft_id: str, session: Session = Depends(get_session)):\n"
        f"    item = session.get({entity}, draft_id)\n"
        f"    if item is None:\n"
        f'        raise HTTPException(status_code=404, detail="{entity} not found")\n'
        f"    cur = getattr(item, {sf!r})\n"
        f"    i = _STEPS.index(cur) if cur in _STEPS else 0\n"
        f"    setattr(item, {sf!r}, _STEPS[max(0, i - 1)])\n"
        f"    session.add(item)\n    session.commit()\n"
        f'    return RedirectResponse(f"/flow/{n}/{{draft_id}}", status_code=303)\n'
    )
    return header + "\n\n" + body


def render_flow_shell(views_text: str, flow: FlowSpec) -> str:
    """``app/templates/flows/<name>/shell.html`` — step indicator + tolerant per-step seam + nav (FR-WZ-3)."""
    n = flow.name
    sf = flow.step_field
    return (
        "{# startd8-artifact: flow-shell — GENERATED; per-step bodies are app-owned #}\n"
        '{% extends "base.html" %}\n'
        "{% block title %}" + n + "{% endblock %}\n"
        "{% block content %}\n"
        f"<h1>{n}</h1>\n"
        f'<p class="flow-step">Step: {{{{ item.{sf} }}}} ({{{{ steps.index(item.{sf}) + 1 }}}}/{{{{ steps|length }}}})</p>\n'
        # per-step body is owned glue; inert until the app provides flows/<name>/_step_<key>.html
        f'{{% include "flows/{n}/_step_" ~ item.{sf} ~ ".html" ignore missing %}}\n'
        f'<form method="post" action="/flow/{n}/{{{{ item.id }}}}/back" style="display:inline">'
        '<button type="submit">Back</button></form>\n'
        f'<form method="post" action="/flow/{n}/{{{{ item.id }}}}/advance" style="display:inline">'
        '<button type="submit">Next</button></form>\n'
        "{% endblock %}\n"
    )


def render_flows(schema_text: str, views_text: str) -> List[Tuple[str, str]]:
    """All flow artifacts as (path, text): per-flow router + shell, plus an aggregator __init__ that
    main.py tolerantly mounts (FR-WZ-5). Empty when no `flows:` declared."""
    schema = parse_prisma_schema(schema_text)
    flows = parse_flows(views_text, known_entities=frozenset(schema.models))
    if not flows:
        return []
    out: List[Tuple[str, str]] = []
    for flow in flows:
        out.append((f"app/flows/{flow.name}.py", render_flow_router(schema_text, views_text, flow)))
        out.append((f"app/templates/flows/{flow.name}/shell.html", render_flow_shell(views_text, flow)))
    # aggregator: a flat `flow_routers` list main.py mounts via one tolerant import (the user_routers pattern)
    imports = "\n".join(f"from .{f.name} import flow_{f.name}_router" for f in flows)
    listing = ", ".join(f"flow_{f.name}_router" for f in flows)
    out.append((
        "app/flows/__init__.py",
        "# GENERATED — flow routers aggregator; main.py mounts `flow_routers` tolerantly.\n"
        + imports + f"\n\nflow_routers = [{listing}]\n",
    ))
    return out
