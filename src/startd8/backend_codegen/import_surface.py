"""FR-IMP-6: the generated import SURFACE — a paste/upload screen over ``app/importer.from_json``.

Emitted only when an ``imports.yaml`` entry declares ``surface: true`` (opt-in). A single
``app/import_surface.py`` web router provides ``GET /import`` (a paste textarea + file upload + a
strict/lossy toggle) and ``POST /import`` (decode → size/UTF-8/extension safety → ``from_json`` →
render the structured :class:`ImportResult`). It **never** silently 302s: every outcome — created/
updated/skipped counts and each error — is rendered back into the page (R3-S5). CSRF posture is
inherited from the app (the generated HTMX forms add none today; this matches them).

Two inputs → two-hash drift (schema + imports.yaml), the ``python-import`` precedent. Mounted
tolerantly by ``main.py`` (``import_surface_router``), a no-op when the module is absent.
"""

from __future__ import annotations

from typing import Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_imports
from .imports_manifest import parse_imports

IMPORT_SURFACE_KIND = "python-import-surface"
IMPORT_SURFACE_PATH = "app/import_surface.py"

# Upload safety (FR-IMP-6): bound the uploaded payload + accept only text-ish extensions.
_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_ALLOWED_EXT = (".json", ".txt")


def surface_enabled(imports_text: Optional[str]) -> bool:
    """True iff any import declares ``surface: true`` (the opt-in gate for emitting the screen)."""
    if not imports_text:
        return False
    try:
        specs = parse_imports(imports_text)
    except ValueError:
        return False
    return any(s.surface for s in specs)


def render_import_surface(
    schema_text: str,
    imports_text: Optional[str],
    source_file: str = "prisma/schema.prisma",
) -> str:
    """Render ``app/import_surface.py`` — the paste/upload import screen (FR-IMP-6)."""
    schema_sha = schema_sha256(schema_text)
    imports_sha = schema_sha256(imports_text or "")
    header = header_imports(source_file, schema_sha, imports_sha, IMPORT_SURFACE_KIND)
    return header + "\n\n" + _BODY.format(
        max_bytes=_MAX_UPLOAD_BYTES,
        allowed_ext=repr(_ALLOWED_EXT),
    )


_BODY = '''from __future__ import annotations

import html
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse

from app.db import get_session
from app.importer import from_json

import_surface_router = APIRouter()

_MAX_UPLOAD_BYTES = {max_bytes}
_ALLOWED_EXT = {allowed_ext}


def _page(body: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'><title>Import data</title></head>"
        "<body><nav><a href='/'>&larr; Home</a></nav><main style='max-width:48rem;margin:2rem auto'>"
        "<h1>Import data</h1>" + body + "</main></body></html>"
    )


_FORM = (
    "<form method='post' action='/import' enctype='multipart/form-data'>"
    "<p>Paste a JSON export, or upload a .json/.txt file.</p>"
    "<textarea name='payload_text' rows='12' style='width:100%' "
    "placeholder='{{\\"Entity\\": [ ... ]}}'></textarea>"
    "<p><input type='file' name='file' accept='.json,.txt'></p>"
    "<p><label><input type='checkbox' name='strict' value='1' checked> "
    "Strict (abort the whole import on any bad row)</label></p>"
    "<p><button type='submit'>Import</button></p>"
    "</form>"
)


@import_surface_router.get("/import", response_class=HTMLResponse)
def import_form(request: Request) -> HTMLResponse:
    """The paste/upload screen."""
    return HTMLResponse(_page(_FORM))


@import_surface_router.post("/import", response_class=HTMLResponse)
async def do_import(
    request: Request,
    session=Depends(get_session),
    payload_text: str = Form(""),
    strict: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
) -> HTMLResponse:
    """Decode the payload (paste or upload), run from_json, render the structured result.

    Never a silent redirect: the ImportResult (counts + every error) is rendered into the page so
    the user sees exactly what happened (R3-S5)."""
    text = payload_text or ""
    if file is not None and file.filename:
        name = file.filename.lower()
        if not name.endswith(_ALLOWED_EXT):
            return HTMLResponse(
                _page(_FORM + f"<p style='color:#b00'>Unsupported file type: "
                      f"{{html.escape(file.filename)}} (allowed: {{', '.join(_ALLOWED_EXT)}})</p>"),
                status_code=400,
            )
        raw = await file.read(_MAX_UPLOAD_BYTES + 1)
        if len(raw) > _MAX_UPLOAD_BYTES:
            return HTMLResponse(
                _page(_FORM + "<p style='color:#b00'>File too large "
                      f"(max {{_MAX_UPLOAD_BYTES // (1024 * 1024)}} MB).</p>"),
                status_code=413,
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return HTMLResponse(
                _page(_FORM + "<p style='color:#b00'>File is not valid UTF-8 text.</p>"),
                status_code=400,
            )

    if not text.strip():
        return HTMLResponse(
            _page(_FORM + "<p style='color:#b00'>Nothing to import — paste JSON or choose a file.</p>"),
            status_code=400,
        )

    result = from_json(text, session, strict=bool(strict))
    rows = (
        f"<li>created: {{result.created}}</li>"
        f"<li>updated: {{result.updated}}</li>"
        f"<li>skipped: {{result.skipped}}</li>"
    )
    if result.errors:
        # Escape every error — they echo payload-derived text (entity names, exception messages),
        # so an unescaped render would be an HTML/JS injection sink (reflected XSS).
        items = "".join(f"<li>{{html.escape(str(e))}}</li>" for e in result.errors)
        errors_html = f"<h2 style='color:#b00'>Errors ({{len(result.errors)}})</h2><ul>{{items}}</ul>"
    else:
        errors_html = "<p style='color:#080'>Import succeeded with no errors.</p>"
    summary = f"<h2>Result</h2><ul>{{rows}}</ul>{{errors_html}}"
    status = 200 if result.ok else 422
    return HTMLResponse(_page(summary + "<hr>" + _FORM), status_code=status)


__all__ = ["import_surface_router"]
'''
