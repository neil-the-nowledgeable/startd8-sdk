"""First-run ``onboarding:`` generation (FR-3/4/5) — welcome route + tips-as-content.

Generated when ``views.yaml`` declares ``onboarding:``:
- ``app/onboarding/welcome.py`` — GET welcome; optional empty-state checklist via live counts
- ``app/templates/onboarding/welcome.html`` — content tips (localStorage dismiss, no modal)
- ``app/onboarding/__init__.py`` — ``onboarding_routers`` aggregator for tolerant main.py mount

Deterministic, $0. PC-13: tips are page content, not a tour library.
"""

from __future__ import annotations

from typing import List, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import parse_prisma_schema
from ._headers import header_forms, header_forms_tmpl
from .onboarding_manifest import OnboardingSpec, parse_onboarding


def _validate(schema, spec: OnboardingSpec) -> None:
    if not spec.route.startswith("/"):
        raise ValueError(f"onboarding: route {spec.route!r} must start with '/'")
    if spec.route.startswith("/ui/"):
        raise ValueError(
            f"onboarding: route {spec.route!r} collides with CRUD /ui/ namespace — choose e.g. /welcome"
        )
    for ent, _copy in spec.empty_states:
        if schema.model(ent) is None:
            raise ValueError(f"onboarding: empty_states unknown entity {ent!r}")


def render_onboarding_welcome_router(schema_text: str, views_text: str) -> str:
    """``app/onboarding/welcome.py``."""
    schema = parse_prisma_schema(schema_text)
    spec = parse_onboarding(views_text, known_entities=frozenset(schema.models))
    if spec is None:
        return "# orphan onboarding welcome: no longer declared in views.yaml `onboarding:`\n"
    _validate(schema, spec)
    header = header_forms(
        "prisma/schema.prisma",
        schema_sha256(schema_text),
        schema_sha256(views_text),
        "fastapi-onboarding",
        entity="welcome",
    )
    imports = ["from app.db import get_session"]
    for ent, _ in spec.empty_states:
        imports.append(f"from app.tables import {ent}")
    import_block = "\n".join(imports)

    checklist_lines = []
    for ent, copy in spec.empty_states:
        ui = f"/ui/{ent.lower()}"
        checklist_lines.append(
            f"    _n = session.exec(select({ent})).all()\n"
            f"    checklist.append({{\n"
            f"        'entity': {ent!r},\n"
            f"        'empty': len(_n) == 0,\n"
            f"        'copy': {copy!r},\n"
            f"        'href': {ui!r},\n"
            f"        'count': len(_n),\n"
            f"    }})\n"
        )
    checklist_body = "".join(checklist_lines) if checklist_lines else "    # no empty_states declared\n"

    # Starlette/FastAPI: TemplateResponse is request-first. The legacy
    # TemplateResponse(name, {"request": request, ...}) form 500s on modern Starlette.
    body = (
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Depends, Request\n"
        "from fastapi.responses import HTMLResponse\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlmodel import Session, select\n\n"
        f"{import_block}\n\n"
        'templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))\n'
        'onboarding_welcome_router = APIRouter(tags=["onboarding"])\n\n'
        f"@onboarding_welcome_router.get({spec.route!r}, response_class=HTMLResponse)\n"
        "def onboarding_welcome(request: Request, session: Session = Depends(get_session)):\n"
        "    checklist = []\n"
        f"{checklist_body}"
        "    # Starlette: request first (same contract as generated pages/web.py).\n"
        "    return templates.TemplateResponse(\n"
        "        request,\n"
        '        "onboarding/welcome.html",\n'
        "        {\n"
        f"            \"title\": {spec.title!r},\n"
        f"            \"lead\": {spec.lead!r},\n"
        f"            \"tips\": {list(spec.tips)!r},\n"
        f"            \"continue_href\": {spec.continue_href!r},\n"
        f"            \"help_href\": {spec.help_href!r},\n"
        f"            \"storage_key\": {spec.storage_key!r},\n"
        "            \"checklist\": checklist,\n"
        "        },\n"
        "    )\n"
    )
    return header + "\n" + body


def render_onboarding_welcome_template(schema_text: str, views_text: str) -> str:
    """``app/templates/onboarding/welcome.html`` — tips as content (PC-13), no modal."""
    schema = parse_prisma_schema(schema_text)
    spec = parse_onboarding(views_text, known_entities=frozenset(schema.models))
    if spec is None:
        return "{# orphan onboarding welcome template #}\n"
    _validate(schema, spec)
    header = header_forms_tmpl(
        "prisma/schema.prisma",
        schema_sha256(schema_text),
        schema_sha256(views_text),
        "onboarding-welcome",
        entity="welcome",
    )
    # Tips: <aside> content + localStorage hide — never role=dialog / modal.
    return (
        header + "\n"
        '{% extends "base.html" %}\n'
        "{% block title %}{{ title }}{% endblock %}\n"
        "{% block content %}\n"
        '<main class="onboarding-welcome">\n'
        "  <h1>{{ title }}</h1>\n"
        '  {% if lead %}<p class="lead">{{ lead }}</p>{% endif %}\n'
        "  {% if tips %}\n"
        '  <aside id="onboarding-tips" class="onboarding-tips" data-storage-key="{{ storage_key }}">\n'
        "    <h2>Tips</h2>\n"
        "    <ul>\n"
        "      {% for tip in tips %}<li>{{ tip }}</li>{% endfor %}\n"
        "    </ul>\n"
        '    <button type="button" id="onboarding-tips-dismiss">Dismiss tips</button>\n'
        "  </aside>\n"
        "  <script>\n"
        "  (function () {\n"
        "    var el = document.getElementById('onboarding-tips');\n"
        "    if (!el) return;\n"
        "    var key = el.getAttribute('data-storage-key') || 'onboarding_tips_dismissed';\n"
        "    try { if (localStorage.getItem(key) === '1') { el.hidden = true; return; } } catch (e) {}\n"
        "    var btn = document.getElementById('onboarding-tips-dismiss');\n"
        "    if (btn) btn.addEventListener('click', function () {\n"
        "      el.hidden = true;\n"
        "      try { localStorage.setItem(key, '1'); } catch (e) {}\n"
        "    });\n"
        "  })();\n"
        "  </script>\n"
        "  {% endif %}\n"
        "  {% if checklist %}\n"
        '  <section class="onboarding-checklist" aria-label="Get started">\n'
        "    <h2>Get started</h2>\n"
        "    <ul>\n"
        "      {% for row in checklist %}\n"
        "      <li>\n"
        "        {% if row.empty %}\n"
        '          <a href="{{ row.href }}">{{ row.copy }}</a>\n'
        "        {% else %}\n"
        "          <span>{{ row.entity }} — {{ row.count }} on file</span>\n"
        '          <a href="{{ row.href }}">Open</a>\n'
        "        {% endif %}\n"
        "      </li>\n"
        "      {% endfor %}\n"
        "    </ul>\n"
        "  </section>\n"
        "  {% endif %}\n"
        '  <p class="onboarding-actions">\n'
        '    <a href="{{ continue_href }}">Continue</a>\n'
        "    {% if help_href %} · <a href=\"{{ help_href }}\">Help</a>{% endif %}\n"
        "  </p>\n"
        "</main>\n"
        "{% endblock %}\n"
    )


def render_onboarding_aggregator(schema_text: str, views_text: str) -> str:
    """``app/onboarding/__init__.py``."""
    header = header_forms(
        "prisma/schema.prisma",
        schema_sha256(schema_text),
        schema_sha256(views_text),
        "onboarding-aggregator",
    )
    spec = parse_onboarding(views_text)
    if spec is None:
        return (
            header + "\n"
            "# onboarding routers aggregator; main.py mounts `onboarding_routers` tolerantly.\n"
            "onboarding_routers = []\n"
        )
    return (
        header + "\n"
        "# onboarding routers aggregator; main.py mounts `onboarding_routers` tolerantly.\n"
        "from .welcome import onboarding_welcome_router\n\n"
        "onboarding_routers = [onboarding_welcome_router]\n"
    )


def render_onboarding(schema_text: str, views_text: str) -> List[Tuple[str, str]]:
    """All onboarding artifacts; empty list when section absent."""
    schema = parse_prisma_schema(schema_text)
    spec = parse_onboarding(views_text, known_entities=frozenset(schema.models))
    if spec is None:
        return []
    _validate(schema, spec)
    return [
        ("app/onboarding/welcome.py", render_onboarding_welcome_router(schema_text, views_text)),
        (
            "app/templates/onboarding/welcome.html",
            render_onboarding_welcome_template(schema_text, views_text),
        ),
        ("app/onboarding/__init__.py", render_onboarding_aggregator(schema_text, views_text)),
    ]
