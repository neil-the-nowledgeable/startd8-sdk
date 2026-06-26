"""M4 — deterministic kickoff web front-end (FastAPI + server-rendered HTML).

A *partial dogfood*: it reuses ``presentation_polish`` theming and renders entirely from the M1
canonical view-model (the same ``KickoffState.to_dict()`` the TUI consumes), so cross-surface parity
(FR-3) is a property of one serializer. It does **not** drive ``flow_generator`` (flows persist only
a step pointer, not values — OQ-2); value capture is its own handler set over the M6 write path.

Endpoints:
    GET  /              — overview: readiness meter, next action, per-field status badges
    GET  /step/{key}    — one step's capture form
    GET  /state.json    — the canonical state snapshot (the parity oracle; M5 consumes the same)
    POST /capture/preview — build a CapturePlan and return its field-scoped diff (R2-S1, no write)
    POST /capture/apply   — apply a capture (CSRF + rate-limit + post-write refresh, R6-S6/R1-S10)

Trust posture (paired with the M7 loopback bind + the M6 allow-list): capture POSTs require a
same-session CSRF token and are per-session rate-limited; typed reason codes (R4-F4) are surfaced.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from .capture import CaptureCode, CaptureError, apply_capture, build_capture_plan
from .docs import live_schema_text, load_kickoff_docs
from .manifest import KickoffExperienceConfig, default_config
from .ranking import next_action
from .readiness import build_readiness
from .state import KickoffState, build_kickoff_state

# Bump when the renderer's output contract changes (part of the freshness fingerprint, R5-S1).
RENDERER_VERSION = "kickoff-web-v1"

# R6-S6 rate limit: max capture POSTs per session per window.
_RATE_MAX = 20
_RATE_WINDOW_S = 60.0
# CSRF/session token idle expiry (R6-S6).
_TOKEN_TTL_S = 3600.0


def app_fingerprint(config: KickoffExperienceConfig, *, theme: str = "professional") -> str:
    """Freshness fingerprint (R5-S1): config + renderer version + theme.

    M7 preflight compares this against a served app's stamp to detect a stale generated app.
    """
    import json

    payload = json.dumps(
        {"config": config.to_dict(), "renderer": RENDERER_VERSION, "theme": theme},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- session / CSRF / rate-limit (in-memory, single-process local app) --------------------------


@dataclass
class _Session:
    token: str
    created: float
    hits: list = field(default_factory=list)  # capture POST timestamps (rate window)


class _SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, _Session] = {}

    def issue(self, now: float) -> str:
        token = secrets.token_urlsafe(24)
        self._sessions[token] = _Session(token=token, created=now)
        return token

    def valid(self, token: Optional[str], now: float) -> bool:
        s = self._sessions.get(token or "")
        if s is None:
            return False
        if now - s.created > _TOKEN_TTL_S:  # idle/expiry (session_expired)
            self._sessions.pop(token, None)
            return False
        return True

    def rate_ok(self, token: str, now: float) -> bool:
        s = self._sessions[token]
        s.hits = [t for t in s.hits if now - t < _RATE_WINDOW_S]
        if len(s.hits) >= _RATE_MAX:
            return False
        s.hits.append(now)
        return True


# --- state assembly (shared with M5 via the canonical view-model) ------------------------------


def load_state(project_root: str | Path) -> KickoffState:
    docs = load_kickoff_docs(project_root)
    return build_kickoff_state(docs, live_schema_text=live_schema_text(project_root))


# --- HTML rendering (server-rendered, themed) --------------------------------------------------

_BADGE = {
    "ok": ("✓", "badge-ok"),
    "review": ("◐", "badge-review"),
    "blocked": ("✗", "badge-blocked"),
    "backlog": ("…", "badge-backlog"),
}


def _esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _page(title: str, body: str, stylesheet: str) -> str:
    extra = (
        ".badge-ok{color:var(--color-success)}.badge-review{color:#b45309}"
        ".badge-blocked{color:var(--color-danger)}.badge-backlog{color:var(--color-muted)}"
        ".meter{height:.6rem;background:var(--color-border);border-radius:4px;overflow:hidden}"
        ".meter>span{display:block;height:100%;background:var(--color-primary)}"
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_esc(title)}</title><style>{stylesheet}\n{extra}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def _render_overview(state: KickoffState, readiness, action, config, stylesheet: str) -> str:
    counts = state.attention_counts
    pct = int(round((readiness.score or 0.0) * 100)) if readiness else 0
    parts = [
        "<h1>Project kickoff</h1>",
        f"<p>Readiness <strong>{pct}%</strong></p>",
        f"<div class='meter'><span style='width:{pct}%'></span></div>",
        f"<p>{_esc(counts.get('ok',0))} ok · {_esc(counts.get('review',0))} review · "
        f"{_esc(counts.get('blocked',0))} blocked · {_esc(counts.get('backlog',0))} backlog</p>",
        f"<div class='card'><h2>Next step</h2><p><strong>{_esc(action.title)}</strong></p>"
        f"<p>{_esc(action.detail)}</p></div>",
        "<h2>Steps</h2><ul>",
    ]
    for step in config.steps:
        parts.append(f"<li><a href='/step/{_esc(step.key)}'>{_esc(step.title)}</a></li>")
    parts.append("</ul><h2>Extraction state</h2><table><thead><tr><th></th><th>Field</th>"
                 "<th>Status</th><th>Detail</th></tr></thead><tbody>")
    for f in state.fields:
        glyph, cls = _BADGE.get(f.attention, ("?", ""))
        detail = f.value if f.value is not None else (f.reason or "")
        parts.append(
            f"<tr><td class='{cls}'>{glyph}</td><td><code>{_esc(f.value_path)}</code></td>"
            f"<td>{_esc(f.attention)}</td><td>{_esc(detail)}</td></tr>"
        )
    parts.append("</tbody></table>")
    return _page("Project kickoff", "".join(parts), stylesheet)


def _render_widget(field, csrf: str) -> str:
    name = _esc(field.value_path)
    if field.widget == "select":
        opts = "".join(f"<option value='{_esc(c)}'>{_esc(c)}</option>" for c in field.choices)
        ctrl = f"<select name='value' id='{name}'>{opts}</select>"
    elif field.widget == "textarea":
        ctrl = f"<textarea name='value' id='{name}'></textarea>"
    elif field.widget == "number":
        ctrl = f"<input type='number' name='value' id='{name}'>"
    elif field.widget == "checkbox":
        ctrl = f"<input type='checkbox' name='value' id='{name}' value='true'>"
    else:
        ctrl = f"<input type='text' name='value' id='{name}'>"
    req = " <span class='req' title='required'>*</span>" if field.required else ""
    return (
        f"<form method='post' action='/capture/apply' class='field'>"
        f"<input type='hidden' name='csrf' value='{_esc(csrf)}'>"
        f"<input type='hidden' name='value_path' value='{name}'>"
        f"<label for='{name}'>{_esc(field.label)}{req}</label>{ctrl}"
        f"<p class='muted'>{_esc(field.grammar_help)}</p>"
        f"<button type='submit'>Save</button></form>"
    )


def _render_step(step, csrf: str, stylesheet: str) -> str:
    parts = [f"<p><a href='/'>← overview</a></p><h1>{_esc(step.title)}</h1>",
             f"<p>{_esc(step.intro)}</p>"]
    for fld in step.fields:
        parts.append(_render_widget(fld, csrf))
    return _page(step.title, "".join(parts), stylesheet)


# --- the app factory ----------------------------------------------------------------------------


def build_kickoff_app(
    project_root: str | Path,
    *,
    config: Optional[KickoffExperienceConfig] = None,
    theme: str = "professional",
    mode: str = "write",
    clock=time.monotonic,
):
    """Build the kickoff web app (FastAPI). Pure function of *project_root* + config + theme.

    *mode* is the R4-F5 feature mode: ``write`` (default) allows applies; ``preview`` /
    ``inspect`` refuse apply (the surface is read/preview only); ``demo`` allows applies on a
    fixture. *clock* is injectable so rate-limit/expiry behavior is testable without real time.
    """
    from fastapi import FastAPI, Form
    from fastapi.responses import HTMLResponse, JSONResponse

    from ..presentation_polish import get_theme, render_stylesheet

    cfg = config or default_config()
    root = str(project_root)
    stylesheet = render_stylesheet(get_theme(theme))
    fingerprint = app_fingerprint(cfg, theme=theme)
    sessions = _SessionStore()

    app = FastAPI(title="StartD8 Kickoff")
    app.state.kickoff_fingerprint = fingerprint

    def _capture_error(exc: CaptureError, http_status: int = 400) -> JSONResponse:
        return JSONResponse(
            {"ok": False, "code": exc.code, "message": str(exc), "value_path": exc.value_path},
            status_code=http_status,
        )

    @app.get("/", response_class=HTMLResponse)
    def overview() -> HTMLResponse:
        state = load_state(root)
        try:
            readiness = build_readiness(root)
        except Exception:
            readiness = None
        action = next_action(state, readiness)
        html = _render_overview(state, readiness, action, cfg, stylesheet)
        resp = HTMLResponse(html)
        # Issue a CSRF/session token cookie (same-origin POSTs echo it via a hidden field).
        token = sessions.issue(clock())
        resp.set_cookie("kickoff_csrf", token, httponly=True, samesite="strict")
        return resp

    @app.get("/state.json")
    def state_json() -> JSONResponse:
        # The parity oracle: byte-identical to what the TUI serializes (R1-S7).
        return JSONResponse(load_state(root).to_dict())

    @app.get("/step/{key}", response_class=HTMLResponse)
    def step(key: str) -> HTMLResponse:
        match = next((s for s in cfg.steps if s.key == key), None)
        if match is None:
            return HTMLResponse("<p>unknown step</p>", status_code=404)
        token = sessions.issue(clock())
        resp = HTMLResponse(_render_step(match, token, stylesheet))
        resp.set_cookie("kickoff_csrf", token, httponly=True, samesite="strict")
        return resp

    @app.post("/capture/preview")
    def capture_preview(value_path: str = Form(...), value: str = Form(...)) -> JSONResponse:
        # Preview is read-only (no CSRF gate needed; it never writes — R2-S1).
        try:
            plan = build_capture_plan(root, value_path, value, config=cfg)
        except CaptureError as exc:
            return _capture_error(exc)
        return JSONResponse({"ok": True, "preview": plan.preview()})

    @app.post("/capture/apply")
    def capture_apply(
        value_path: str = Form(...),
        value: str = Form(...),
        csrf: str = Form(...),
    ) -> JSONResponse:
        # Feature-mode gate (R4-F5): preview/inspect modes cannot reach apply_write_plan.
        if mode in ("preview", "inspect"):
            return JSONResponse(
                {"ok": False, "code": "preview_only",
                 "message": f"mode {mode!r} is read/preview only; use /capture/preview"},
                status_code=403,
            )
        now = clock()
        if not sessions.valid(csrf, now):
            return JSONResponse(
                {"ok": False, "code": "session_expired", "message": "invalid or expired token"},
                status_code=403,
            )
        if not sessions.rate_ok(csrf, now):
            return JSONResponse(
                {"ok": False, "code": "rate_limited", "message": "too many captures; slow down"},
                status_code=429,
            )
        try:
            plan = build_capture_plan(root, value_path, value, config=cfg)
            apply_capture(root, plan)
        except CaptureError as exc:
            status = 409 if exc.code == CaptureCode.STALE_FILE else 400
            return _capture_error(exc, http_status=status)
        # Post-write refresh (R1-S10): re-run extraction so the badge flips immediately.
        state = load_state(root)
        fs = next((f for f in state.fields if f.value_path == plan.value_path), None)
        return JSONResponse(
            {
                "ok": True,
                "code": CaptureCode.OK,
                "value_path": plan.value_path,
                "applied": plan.preview(),
                "refreshed_status": fs.attention if fs else None,
            }
        )

    return app
