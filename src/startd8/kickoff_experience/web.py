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

import asyncio
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional

from .capture import CaptureCode, CaptureError, apply_capture, build_capture_plan
from .manifest import KickoffExperienceConfig, default_config
from .ranking import next_action
from .readiness import build_readiness
from .state import KickoffState, resolve_kickoff_state

# Bump when the renderer's output contract changes (part of the freshness fingerprint, R5-S1).
RENDERER_VERSION = "kickoff-web-v1"

# R6-S6 rate limit: max capture POSTs per session per window.
_RATE_MAX = 20
_RATE_WINDOW_S = 60.0
# CSRF/session token idle expiry (R6-S6).
_TOKEN_TTL_S = 3600.0
# Welcome Mat 2.0 bundle ceiling (FR-WM2-3): fail closed before allocating an oversized in-memory zip.
# 2 MiB is ample for the ~11-file template set; a manifest-bloat regression returns 413, never a partial.
_BUNDLE_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
# Welcome Mat 2.0 chat input cap (FR-WM2-5b): reject an oversized message before any provider call.
_MAX_CHAT_MESSAGE_CHARS = 4096
# GE-M5 (FR-GE-8) — cloud is READ/PREVIEW-ONLY. Cloud-WRITE is intentionally **not built**: a cloud
# (non-loopback) surface has no per-tenant trust substrate — only the static `server/auth.py`
# `X-API-Key` (no principal/tenancy/session/CSRF). So every write + LLM-invoking (facilitation/chat)
# endpoint is refused in cloud mode with a typed **501** carrying this code, making the deferral
# explicit and discoverable rather than a silent 403/404. Building cloud-write needs the net-new
# auth/tenancy/CSRF design tracked as **OQ-GE-7** (see GUIDED_EXPERIENCE_REQUIREMENTS.md FR-GE-8 /
# OQ-GE-7). The human downloads produced inputs and writes locally (FR-GE-13/14: human/CLI is the
# sole writer). Deepen stays static-transcript-only on cloud: `/guided` reads only persisted
# `.startd8/kickoff-panel/*` sessions via `build_guided_view(load_deepen=True)` and invokes no LLM.
CLOUD_WRITE_DEFERRED_CODE = "cloud_write_deferred"

# M1 (FR-13 / R1-S2) — the structural default-deny registry. On cloud, a POST must be classified as
# EITHER a read/preview route (allowed) OR a write/chat route that consults the `_cloud_capability` seam
# (which decides allow/deny). Any POST in neither set is an **un-classified write → deny 501** (a new
# route that forgets the seam fails CLOSED, not open). Keep in lockstep with the actual routes — a test
# asserts every `@app.post` is in exactly one set.
_CLOUD_READONLY_POSTS = frozenset({
    "/capture/preview",
    "/concierge/instantiate/preview",
    "/concierge/chat/pending",
    "/concierge/chat/discard",
})
_CLOUD_SEAM_GATED_POSTS = frozenset({
    "/capture/apply",
    "/audience/set",
    "/concierge/instantiate",
    "/concierge/friction",
    "/concierge/chat/message",
    "/concierge/chat/confirm",
    "/concierge/chat/reset",
})

# stop_reason → typed /chat code (FR-WM2-8b); `completed` is the only non-refusal outcome.
_CHAT_STOP_CODE = {
    "budget": "chat_budget_exceeded",
    "max_turns": "chat_max_turns",
    "repeated_calls": "chat_repeated_calls",
    "context_overflow": "chat_context_overflow",
    "stream_error": "chat_stream_error",
}


def _chat_cost_block(chat, result) -> dict:
    """The stable structured `cost` on a /chat response (FR-WM2-9 / R3-F7) — one machine contract the
    inline panel client consumes, plus a human-readable `line`. Never carries the user message."""
    return {
        "turns": getattr(result, "turns", None),
        "tokens": getattr(result, "total_tokens", None),
        "usd": getattr(result, "total_cost_usd", None),
        "stop_reason": getattr(result, "stop_reason", None),
        "line": chat.cost_line(result),
    }


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

    def _prune(self, now: float) -> None:
        """Drop expired sessions so a long-running local server doesn't leak tokens."""
        expired = [t for t, s in self._sessions.items() if now - s.created > _TOKEN_TTL_S]
        for t in expired:
            self._sessions.pop(t, None)

    def issue(self, now: float) -> str:
        self._prune(now)
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
        s = self._sessions.get(token)
        if s is None:  # token expired/evicted between valid() and here — treat as not allowed
            return False
        s.hits = [t for t in s.hits if now - t < _RATE_WINDOW_S]
        if len(s.hits) >= _RATE_MAX:
            return False
        s.hits.append(now)
        return True


# --- state assembly (shared with M5 via the canonical view-model) ------------------------------


def load_state(project_root: str | Path) -> KickoffState:
    return resolve_kickoff_state(project_root)


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


def _template_media_type(dest: str) -> str:
    """Content type for a downloaded template (R2-S8): YAML/Markdown, always utf-8."""
    if dest.endswith((".yaml", ".yml")):
        return "text/yaml; charset=utf-8"
    if dest.endswith(".md"):
        return "text/markdown; charset=utf-8"
    return "text/plain; charset=utf-8"


def _render_templates(entries, posture: str, stylesheet: str) -> str:
    """The read-only download index (FR-WM2-1): grouped list + posture selector + bundle links."""
    from ..concierge.writes import render_template_content

    parts = [
        "<h1>Kickoff templates</h1>",
        "<p>Download the kickoff-input and authoring templates — read-only, $0. "
        "These are the same files the Concierge would scaffold into a project.</p>",
        "<p><a href='/'>← back to kickoff</a></p>",
        "<form method='get' action='/templates'><label>Posture "
        "<select name='posture' onchange='this.form.submit()'>",
    ]
    for p in ("prototype", "production"):
        sel = " selected" if p == posture else ""
        parts.append(f"<option value='{_esc(p)}'{sel}>{_esc(p)}</option>")
    parts.append("</select></label></form>")
    parts.append(
        f"<p><a href='/templates/bundle.zip?posture={_esc(posture)}&amp;with_authoring=true'>"
        "⬇ Download all (zip)</a> · "
        f"<a href='/templates/bundle.zip?posture={_esc(posture)}&amp;with_authoring=false'>"
        "package only</a></p>"
    )
    for group in ("package", "authoring"):
        parts.append(
            f"<h2>{_esc(group)}</h2><table><thead><tr><th>Template</th><th>Destination</th>"
            "<th>Bytes</th></tr></thead><tbody>"
        )
        for e in (x for x in entries if x.group == group):
            nbytes = len(render_template_content(e, posture).encode("utf-8"))
            href = f"/templates/file/{_esc(e.key)}?posture={_esc(posture)}"
            parts.append(
                f"<tr><td><a href='{href}'>{_esc(e.label)}</a></td>"
                f"<td><code>{_esc(e.dest)}</code></td><td>{nbytes}</td></tr>"
            )
        parts.append("</tbody></table>")
    return _page("Kickoff templates", "".join(parts), stylesheet)


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


def _concierge_cta(concierge_view) -> str:
    """The home-page Concierge entry (R2-S7). When the shared view-model reports a package is
    missing/partial (`instantiate_offer.needed`), surface its own `next_action` as a prominent CTA —
    reusing `build_concierge_view`'s decision rather than re-detecting package state here. Otherwise
    fall back to the generic link. `concierge_view` is optional so the renderer degrades to the link."""
    offer = (concierge_view or {}).get("instantiate_offer") or {}
    if offer.get("needed"):
        na = (concierge_view or {}).get("next_action") or {}
        title = na.get("title") or "Create the kickoff package"
        detail = na.get("detail") or "This project has no kickoff inputs yet."
        return (
            f"<div class='card'><h2>🛈 {_esc(title)}</h2><p>{_esc(detail)}</p>"
            "<p><a href='/concierge'>Open Concierge →</a></p></div>"
        )
    return ("<p><a href='/concierge'>🛈 Concierge — survey, instantiate a kickoff package, "
            "log friction</a></p>")


def _render_overview(state: KickoffState, readiness, action, config, stylesheet: str,
                     concierge_view=None) -> str:
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
        # Red Carpet entry (discoverability): the staged, agentic build-from-scratch experience.
        "<div class='card'><h2>🟥 Build my app from scratch</h2>"
        "<p>The Red Carpet Treatment walks you from an idea to a buildable app — co-author the data "
        "model, then the pages/views/inputs the $0 cascade needs. You confirm every write.</p>"
        "<p><a href='/concierge/chat'>Start the Red Carpet build →</a></p></div>",
        _concierge_cta(concierge_view),
        "<p><a href='/templates'>⬇ Download kickoff templates</a></p>",
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


# --- Concierge mode (M-CM3): hardening helpers + renderer ---------------------------------------

# Clickjacking / UI-redress defense for the local write surface (R5-S2).
_FRAME_DENY_HEADERS = {
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "frame-ancestors 'none'",
}
# DNS-rebinding defense (R1-S8): a local app must only answer for loopback Host names.
_ALLOWED_HOSTS = ("127.0.0.1", "localhost")


def _host_ok(host_header: Optional[str]) -> bool:
    """True if the request's Host is a loopback name (defeats DNS-rebinding)."""
    if not host_header:
        return False
    hostname = host_header.split(":", 1)[0].strip().lower()
    return hostname in _ALLOWED_HOSTS


class _IntentStore:
    """One-time apply-intents (R3-S1): a preview issues an intent bound to (action, digest); apply
    consumes it exactly once, so a double-submit/replay does not write twice.

    Bounded (FIFO) so abandoned intents — a Concierge page viewed but never applied — cannot grow
    without limit on a long-running local server.
    """

    _MAX = 256

    def __init__(self) -> None:
        self._intents: Dict[str, tuple] = {}

    def issue(self, action: str, digest: str) -> str:
        token = secrets.token_urlsafe(18)
        if len(self._intents) >= self._MAX:
            self._intents.pop(next(iter(self._intents)), None)  # evict oldest
        self._intents[token] = (action, digest)
        return token

    def consume(self, token: Optional[str], action: str, digest: str) -> bool:
        rec = self._intents.pop(token or "", None)
        return rec is not None and rec == (action, digest)


def _plan_digest(plan: dict) -> str:
    paths = sorted(w.get("path", "") for w in plan.get("writes", []))
    return hashlib.sha256((plan.get("action", "") + "|" + "|".join(paths)).encode()).hexdigest()[:16]


class _ChatStore:
    """Bounded per-app store of live agentic chat sessions, keyed by the **`kickoff_chat`** session id
    (a server-issued httponly cookie, FR-WM2-5a) — distinct from the `kickoff_csrf` write token.

    History lives in RAM only and is **destroyed on eviction or idle expiry** (FR-WM2-5d): the
    `AgenticSession.messages` list is cleared so a stale session never lingers in memory."""

    _MAX = 16
    _IDLE_S = 1800.0   # 30-min idle expiry (FR-WM2-5d)

    def __init__(self, clock: "Callable[[], float]" = time.monotonic) -> None:
        self._clock = clock
        self._chats: Dict[str, list] = {}   # token -> [chat, last_used]

    @staticmethod
    def _wipe(chat: object) -> None:
        """Destroy the in-RAM conversation history (never persisted)."""
        msgs = getattr(getattr(chat, "session", None), "messages", None)
        if isinstance(msgs, list):
            msgs.clear()

    def _prune(self, now: float) -> None:
        for tok in [t for t, (_, used) in self._chats.items() if now - used > self._IDLE_S]:
            self._wipe(self._chats.pop(tok)[0])

    def put(self, token: str, chat: object) -> None:
        now = self._clock()
        self._prune(now)
        if len(self._chats) >= self._MAX:
            self._wipe(self._chats.pop(next(iter(self._chats)))[0])   # evict + wipe oldest
        self._chats[token] = [chat, now]

    def get(self, token: str):
        now = self._clock()
        self._prune(now)
        entry = self._chats.get(token)
        if entry is None:
            return None
        entry[1] = now   # touch
        return entry[0]

    def discard(self, token: Optional[str]) -> None:
        """Drop + wipe a session's history (new-conversation reset, R4-F6)."""
        entry = self._chats.pop(token or "", None)
        if entry is not None:
            self._wipe(entry[0])


def _render_chat_page(csrf: str, stylesheet: str) -> str:
    """The agentic Concierge chat panel — message box + transcript + pending proposals.

    The chat **session** rides the httponly `kickoff_chat` cookie (FR-WM2-5a), so it is never embedded
    in the page or readable by JS; only the write-gate `csrf` token is rendered in. `fetch` uses
    ``credentials:'same-origin'`` so the cookie accompanies each POST."""
    body = (
        "<p><a href='/concierge'>← Concierge</a></p><h1>Concierge — chat</h1>"
        "<p class='muted'>I survey/assess and can RECOMMEND actions. I never write to disk: you "
        "confirm each recommendation before it applies.</p>"
        # Red Carpet stage rail (FR-RCT, OQ-4): the staged build map, refreshed from /red-carpet.json.
        "<div id='rail' class='card'></div>"
        "<div id='log' class='card' style='min-height:8rem'></div>"
        "<div id='proposals'></div>"
        "<form id='f' class='field'><input id='msg' name='msg' placeholder='ask about the kickoff…' "
        "autocomplete='off' style='width:80%'><button type='submit'>Send</button></form>"
        "<p><button type='button' id='reset'>New conversation</button></p>"
        f"<script>const CSRF={csrf!r};const OPTS={{method:'POST',credentials:'same-origin'}};\n"
        "const log=document.getElementById('log'),prop=document.getElementById('proposals'),"
        "rail=document.getElementById('rail');\n"
        "function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}\n"
        "function add(who,t){log.innerHTML+=`<p><strong>${who}:</strong> ${esc(t)}</p>`;log.scrollTop=log.scrollHeight;}\n"
        "function renderProposals(ps){prop.innerHTML=ps.length?'<h3>Proposed (confirm to apply)</h3>':'';\n"
        " ps.forEach(p=>{const id=esc(p.id);prop.innerHTML+=`<div class='card'><pre>${esc(p.summary)}</pre>`+\n"
        "  `<button onclick=\"act('confirm','${id}')\">Confirm</button> `+\n"
        "  `<button onclick=\"act('discard','${id}')\">Discard</button><div id='r-${id}'></div></div>`;});}\n"
        "async function refreshRail(){try{const j=await (await fetch('/red-carpet.json')).json();\n"
        "  const rows=(j.stages||[]).map(s=>`<div>${s.status==='done'?'✓':'…'} <strong>${esc(s.key)}</strong>`+\n"
        "    `${s.key===j.next_stage?' (next)':''} — ${esc(s.detail)}</div>`).join('');\n"
        "  const pv=(j.cascade_offerable&&j.preview)?`<p class='muted'>preview: shape ${esc(j.preview.shape||'')}</p>`:'';\n"
        "  const foot=j.cascade_offerable?`<p><strong>The $0 cascade is offerable.</strong></p>${pv}`:\n"
        "    `<p class='muted'>cascade not offerable — unmet: ${esc((j.unmet_gates||[]).join(', '))}</p>`;\n"
        # FR-RCA-11 — insights + ranked next steps; every field HTML-escaped via esc() (CRP R1-S4:
        # advisory detail can carry an invalid-YAML error string read off disk).
        "  const adv=(j.advisories||[]).map(a=>`<div>[${esc(a.severity)}] <strong>${esc(a.title)}</strong>`+\n"
        "    ` — ${esc(a.detail)}${a.command?` <code>${esc(a.command)}</code>`:''}</div>`).join('');\n"
        "  const advh=adv?`<h4>Insights</h4>${adv}`:'';\n"
        "  const ns=(j.next_steps||[]).map(s=>`<div>${esc(String(s.rank))}. ${esc(s.title)}`+\n"
        "    `${s.command?` <code>${esc(s.command)}</code>`:''}</div>`).join('');\n"
        "  const nsh=ns?`<h4>Next steps</h4>${ns}`:'';\n"
        "  rail.innerHTML=`<h3>Build progress</h3>${rows}${foot}${advh}${nsh}`;}catch(e){}}\n"
        "async function act(kind,id){const fd=new FormData();fd.append('proposal_id',id);fd.append('csrf',CSRF);\n"
        " const r=await fetch('/concierge/chat/'+kind,{...OPTS,body:fd});const j=await r.json();\n"
        " document.getElementById('r-'+id).innerHTML=esc(kind==='confirm'?(j.code+': '+(j.detail||'')):'discarded');\n"
        " refresh();refreshRail();}\n"
        "async function refresh(){\n"
        " const r=await fetch('/concierge/chat/pending',{...OPTS,body:new FormData()});renderProposals((await r.json()).proposals||[]);}\n"
        "document.getElementById('f').onsubmit=async e=>{e.preventDefault();const m=document.getElementById('msg').value;\n"
        " if(!m)return;document.getElementById('msg').value='';add('you',m);add('…','thinking');\n"
        " const fd=new FormData();fd.append('message',m);\n"
        " const r=await fetch('/concierge/chat/message',{...OPTS,body:fd});const j=await r.json();\n"
        " log.lastChild.remove();add('concierge',j.ok?j.text:('error: '+(j.message||j.code)));\n"
        " renderProposals(j.proposals||[]);refreshRail();};\n"
        "document.getElementById('reset').onclick=async()=>{const fd=new FormData();fd.append('csrf',CSRF);\n"
        " await fetch('/concierge/chat/reset',{...OPTS,body:fd});log.innerHTML='';prop.innerHTML='';refreshRail();};\n"
        "refreshRail();\n"
        "</script>"
    )
    return _page("Concierge — chat", body, stylesheet)


def _render_concierge(view: dict, csrf: str, intents: dict, stylesheet: str) -> str:
    """Render the shared Concierge view-model (the same payload the TUI renders)."""
    s = view["survey"]
    offer = view["instantiate_offer"]
    na = view["next_action"]
    parts = [
        "<p><a href='/'>← overview</a></p><h1>Concierge</h1>",
        f"<p class='muted'>{_esc(view['posture_banner'])}</p>",
        "<p><a href='/concierge/chat'>💬 Chat with the Concierge — conversational, recommends "
        "actions you confirm</a></p>",
        f"<div class='card'><h2>Next step</h2><p><strong>{_esc(na['title'])}</strong></p>"
        f"<p>{_esc(na['detail'])}</p></div>",
        "<h2>Survey — brownfield triage</h2>",
        f"<p>Requirement/PRD docs: <strong>{len(s.get('requirement_docs', []))}</strong> · "
        f"model files: <strong>{len(s.get('model_files', []))}</strong> · "
        f"fixtures: <strong>{len(s.get('fixture_candidates', []))}</strong> · "
        f"PII risk flags: <strong>{len(s.get('pii_risk_flags', []))}</strong></p>",
    ]
    docs = s.get("requirement_docs", [])
    if docs:
        parts.append("<table><thead><tr><th>Doc</th><th>Extraction format?</th></tr></thead><tbody>")
        for d in docs:
            ok = d.get("extraction_format")
            parts.append(f"<tr><td><code>{_esc(d.get('path'))}</code></td>"
                         f"<td>{'✓' if ok else '✗ needs reformat'}</td></tr>")
        parts.append("</tbody></table>")
    # Instantiate offer
    parts.append(f"<h2>Kickoff package — {_esc(offer['package_state'])}</h2>")
    if offer["needed"]:
        opts = "".join(f"<option value='{p}'>{p}</option>" for p in offer["postures"])
        parts.append(
            "<form method='post' action='/concierge/instantiate' class='field'>"
            f"<input type='hidden' name='csrf' value='{_esc(csrf)}'>"
            f"<input type='hidden' name='intent' value='{_esc(intents['instantiate'])}'>"
            f"<label>Posture <select name='posture'>{opts}</select></label>"
            "<button type='submit'>Create / complete kickoff package</button></form>"
        )
    else:
        parts.append("<p class='muted'>The kickoff package is complete.</p>")
    # Friction form
    parts.append("<h2>Log friction</h2><form method='post' action='/concierge/friction' class='field'>"
                 f"<input type='hidden' name='csrf' value='{_esc(csrf)}'>"
                 f"<input type='hidden' name='intent' value='{_esc(intents['friction'])}'>")
    for fld in view["friction_form"]["fields"]:
        parts.append(f"<label>{_esc(fld['label'])}"
                     f"<textarea name='{_esc(fld['name'])}' maxlength='{fld['max_length']}'></textarea></label>")
    parts.append("<button type='submit'>Log friction</button></form>")
    return _page("Concierge", "".join(parts), stylesheet)


def _render_guided(view: dict, stylesheet: str) -> str:
    """Render the shared guided view-model (GE-M4) as HTML — the SAME payload the CLI and TUI render.

    The served leg is read/preview-only: it presents Orient → Guide → Deepen (incl. GE-M3b's
    halted-session + per-round/total-cost states) but invokes no LLM and writes nothing. Parity is a
    property of `build_guided_view`; this function differs from the CLI/TUI only in *rendering*.
    """
    from .concierge_view import format_cost

    orient = view.get("orient") or {}
    guide = view.get("guide") or {}
    deepen = view.get("deepen") or {}
    intro = view.get("intro") or {}
    posture = view.get("posture") or {}
    parts = [
        "<p><a href='/'>← overview</a></p><h1>Guided kickoff</h1>",
        "<p class='muted'>One experience, three phases — Orient → Guide → Deepen "
        "(read-only, $0, no LLM).</p>",
    ]
    # Intro (clause A) — the same process intro the CLI/TUI lead with (full on a first run, else a
    # one-line pointer). Rendered ahead of Orient so the served surface orients too (parity).
    if intro.get("text"):
        parts.append(f"<div class='card'><p>{_esc(intro['text'])}</p></div>")
    # Orient
    parts.append("<h2>1. Orient — where you are (readiness)</h2>")
    score = guide.get("readiness_score")
    if score is not None:
        parts.append(f"<p>Readiness score: <strong>{_esc(score)}</strong></p>")
    domains = ((orient.get("kickoff_inputs") or {}).get("domains")) or {}
    if domains:
        parts.append("<ul>")
        for name, info in domains.items():
            parts.append(f"<li><code>{_esc(name)}</code>: {_esc(info.get('status'))}</li>")
        parts.append("</ul>")
    unmet = guide.get("unmet_gates") or []
    parts.append(f"<p>Unmet gates: {_esc(', '.join(unmet) if unmet else '(none)')}</p>")
    # Posture (clause B) — information only; points at the actionable `instantiate --posture`.
    if posture.get("actionable_hint"):
        cur = posture.get("current_mode")
        state = f"current mode = {cur}" if cur else "not yet chosen"
        parts.append(
            f"<p>Posture: {_esc(state)} — set it when you instantiate: "
            f"<code>{_esc(posture['actionable_hint'])}</code></p>"
        )
    # Guide
    parts.append("<h2>2. Guide — the $0 conductor (deterministic, no LLM)</h2>")
    steps = guide.get("steps") or []
    if steps:
        parts.append("<ol>")
        for s in steps:
            cmd = s.get("command")
            cmd_html = f" <code>{_esc(cmd)}</code>" if cmd else ""
            parts.append(
                f"<li>[{_esc(s.get('cost'))}] {_esc(s.get('title'))} "
                f"({_esc(s.get('stage'))}){cmd_html}</li>"
            )
        parts.append("</ol>")
    else:
        parts.append("<p class='muted'>No next steps — the $0 cascade is build-ready.</p>")
    # Deepen — the same halt/cost projection every surface shows
    parts.append("<h2>3. Deepen — optional multi-perspective facilitation</h2>")
    if deepen.get("engaged"):
        parts.append(
            f"<p>Session <code>{_esc(deepen.get('session_id'))}</code> — "
            f"status: <strong>{_esc(deepen.get('status'))}</strong></p>"
        )
        if deepen.get("halted") and deepen.get("halt"):
            parts.append(
                "<div class='card'><h3>⛔ HALTED "
                f"({_esc(deepen['halt'].get('reason'))})</h3>"
                f"<p>{_esc(deepen['halt'].get('message'))}</p></div>"
            )
        cap = deepen.get("budget_usd") or 0.0
        cap_str = f" of {format_cost(cap)} cap" if cap else ""
        parts.append(
            f"<p>Cost: <strong>{_esc(format_cost(deepen.get('cost_total_usd')))}</strong>"
            f"{_esc(cap_str)} over {_esc(deepen.get('n_rounds'))} round(s)</p>"
        )
    else:
        parts.append(
            "<p class='muted'>Optional — drive the facilitation panel via "
            f"<code>{_esc(deepen.get('surface'))}</code> (paid, synthetic — unratified input). "
            "Nothing is spent or written here.</p>"
        )
    return _page("Guided kickoff", "".join(parts), stylesheet)


# --- the app factory ----------------------------------------------------------------------------


def _mirror_session_to_cockpit(project_root: str, chat: object) -> None:
    """Persist this LOCAL agentic session so the read-only cockpit can mirror it (the loop-closer).

    FR-WM2-5d **softened for local single-user** (loopback, non-cloud): the strict RAM-only/no-disk
    contract still governs the hosted/``--cloud`` posture (which disables chat entirely, so this is
    never reached there), but a *local* user's own session MAY be persisted — **redacted** — to their
    own project ``.startd8/`` so the Assistant + Proposals cockpit tabs populate. Writes:
      * the redacted FR-1 snapshot (transcript + cost + pending ids) via ``persist_snapshot_for_chat``;
      * the VIPP inbox (``serialize_buffer(force=True)``) so the Proposals tab has the current buffer
        (last-writer-wins, matching the snapshot's last-session-only semantic).
    Fully best-effort — a mirror hiccup never breaks the chat turn.
    """
    try:
        from .session_snapshot import persist_snapshot_for_chat

        persist_snapshot_for_chat(project_root, chat)
    except Exception:  # pragma: no cover - mirror is never load-bearing
        pass
    try:
        from .vipp_seam import serialize_buffer

        buf = getattr(chat, "buffer", None)
        if buf is not None:
            serialize_buffer(buf, project_root, force=True)
    except Exception:  # pragma: no cover - mirror is never load-bearing
        pass


def build_kickoff_app(
    project_root: str | Path,
    *,
    config: Optional[KickoffExperienceConfig] = None,
    theme: str = "professional",
    mode: str = "write",
    clock=time.monotonic,
    chat_factory: "Optional[Callable[[], object]]" = None,
    cloud: bool = False,
    api_key: Optional[str] = None,
    mirror_cockpit: bool = False,
    grant_store: "Optional[object]" = None,
    deployment_id: str = "",
    project_id: Optional[str] = None,
    cloud_origins: "frozenset[str]" = frozenset(),
    grant_clock: "Optional[Callable[[], float]]" = None,
):
    """Build the kickoff web app (FastAPI). Pure function of *project_root* + config + theme.

    *mode* is the R4-F5 feature mode: ``write`` (default) allows applies; ``preview`` /
    ``inspect`` refuse apply (the surface is read/preview only); ``demo`` allows applies on a
    fixture. *clock* is injectable so rate-limit/expiry behavior is testable without real time.

    *cloud* (GE-M5, FR-GE-8) puts the served surface in **cloud read/preview-only** posture,
    orthogonal to and stronger than *mode*: **every write and LLM-invoking (facilitation/chat)
    endpoint is refused** with a typed 501 (``cloud_write_deferred``) because a cloud surface has
    no per-tenant trust substrate — cloud-write is deferred to OQ-GE-7. Reads (Orient + Guide +
    the static-transcript-only Deepen view) stay open. When *api_key* is set on a cloud app, the
    static ``server/auth.py`` ``X-API-Key`` middleware gates mutation (POST) requests — reused as
    the coarse cloud auth, **not** a new tenancy model (OQ-GE-7).
    """
    from fastapi import Cookie, FastAPI, Form, Header, Query
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    from ..presentation_polish import get_theme, render_stylesheet

    cfg = config or default_config()
    root = str(project_root)
    # M2 (FR-13/FR-14): the ONE effective-posture decision. local → allow; cloud + no grant store →
    # strict deny (== today); cloud + a grant store + a request trust-chain context → the FR-14 ordered
    # AND-gate (api-key ∧ Origin ∧ live-grant), consuming one use on allow (session-creation, FR-15).
    _grant_store = grant_store
    _deployment_id = deployment_id
    _project_id = project_id if project_id is not None else Path(root).name
    _cloud_origins = cloud_origins
    _grant_clock = grant_clock or time.time
    _NO_CTX = object()   # sentinel: a gate that supplies no trust-chain context (not grant-authorized)
    _session_grants: "Dict[str, tuple]" = {}   # M3: chat_sid -> (grant_id, GrantTarget) for revalidation

    def _cloud_capability(capability: str, *, req_api_key=_NO_CTX, req_origin=_NO_CTX):
        """The ONE effective-posture decision (FR-13), returning a `GrantDecision`. local → allow;
        cloud + no grant store / no context → deny; cloud + context → the FR-14 trust chain, which
        **CONSUMES one use** on allow (session creation, FR-15). The returned `grant_id` binds the session
        for M3 per-turn revalidation. Per-turn gates use :func:`_cloud_revalidate` (no consume)."""
        from .cloud_grant import (
            GrantDecision, GrantDeny, GrantTarget, TrustChainInputs, evaluate_trust_chain,
        )
        if not cloud:
            return GrantDecision(True)        # local → allow (today's behavior)
        if _grant_store is None or req_api_key is _NO_CTX:
            return GrantDecision.deny(GrantDeny.ABSENT)   # cloud + no store / no context → strict deny
        target = GrantTarget(deployment_id=_deployment_id, project_id=_project_id, capability=capability)
        inputs = TrustChainInputs(
            api_key_expected=api_key, api_key_presented=req_api_key,
            allowed_origins=_cloud_origins, origin_presented=req_origin,
        )
        return evaluate_trust_chain(_grant_store, target, inputs, now=_grant_clock())

    def _cloud_revalidate(kickoff_chat: Optional[str], req_origin: Optional[str]) -> bool:
        """M3 per-turn re-validation (R1-S9/FR-15): a cloud chat turn/apply is permitted iff the session's
        bound grant is **still live** (no consume) AND the Origin is configured. api-key is enforced by
        `APIKeyMiddleware` on the POST. So a session created just before expiry/revocation is denied on its
        next action — consuming the use at creation buys no unbounded post-expiry session."""
        if not cloud:
            return True
        if _grant_store is None:
            return False
        if not _cloud_origins or req_origin not in _cloud_origins:
            return False
        binding = _session_grants.get(kickoff_chat or "")
        if binding is None:
            return False                      # a cloud session with no grant binding → deny
        grant_id, target = binding
        return _grant_store.revalidate(grant_id, target, now=_grant_clock()).allowed

    # GE-M5 cloud read-only guard: with no grant store, cloud disables the LLM-invoking agentic panel at
    # build time (an un-metered spend surface). M2's grant-capable build keeps the factory + gates
    # per-request; in M1 `_grant_store is None`, so this is exactly the previous `if cloud:` behavior.
    if cloud and _grant_store is None:
        chat_factory = None
        mirror_cockpit = False   # hosted stays strict (FR-WM2-5d): no chat, no disk mirror

    def _cloud_deferred(what: str = "write") -> "JSONResponse":
        """The explicit OQ-GE-7 refusal: cloud is read/preview-only; *what* is deferred (501)."""
        return JSONResponse(
            {
                "ok": False,
                "code": CLOUD_WRITE_DEFERRED_CODE,
                "message": (
                    f"cloud is read/preview-only; {what} is deferred to OQ-GE-7 "
                    "(net-new auth/tenancy). Download inputs and write locally."
                ),
            },
            status_code=501,
            headers=dict(_FRAME_DENY_HEADERS),
        )
    stylesheet = render_stylesheet(get_theme(theme))
    fingerprint = app_fingerprint(cfg, theme=theme)
    sessions = _SessionStore()

    app = FastAPI(title="StartD8 Kickoff")
    app.state.kickoff_fingerprint = fingerprint
    intents = _IntentStore()  # one-time apply intents for Concierge writes (R3-S1)
    chats = _ChatStore(clock=clock)   # live agentic chat sessions (web agentic panel); idle-expiring
    chat_locks: Dict[str, asyncio.Lock] = {}   # FR-WM2-5c: one in-flight turn per chat session
    app.state.kickoff_agentic_enabled = chat_factory is not None
    app.state.kickoff_cloud = cloud  # GE-M5 read-only posture (introspectable by preflight/tests)

    @app.middleware("http")
    async def _cloud_write_default_deny(request, call_next):
        """Structural default-deny (R1-S2): on cloud, a POST that is neither a known read/preview route
        nor a seam-gated write route is an **un-classified write → 501**. Existing routes are covered by
        the two sets (unaffected, byte-identical); a NEW write route that forgets the `_cloud_capability`
        seam fails CLOSED. A pure pass-through for non-cloud + for GET."""
        if cloud and request.method == "POST":
            p = request.url.path
            if p not in _CLOUD_READONLY_POSTS and p not in _CLOUD_SEAM_GATED_POSTS:
                return _cloud_deferred("write")
        return await call_next(request)

    def _capture_error(exc: CaptureError, http_status: int = 400) -> JSONResponse:
        return JSONResponse(
            {"ok": False, "code": exc.code, "message": str(exc), "value_path": exc.value_path},
            status_code=http_status,
        )

    @app.get("/", response_class=HTMLResponse)
    def overview() -> HTMLResponse:
        from .concierge_view import build_concierge_view

        state = load_state(root)
        try:
            readiness = build_readiness(root)
        except Exception:
            readiness = None
        action = next_action(state, readiness)
        try:
            # Shared view-model (TTL-memoized survey) drives the Concierge CTA; never break the
            # overview if it degrades (R2-S7).
            concierge_view = build_concierge_view(root)
        except Exception:
            concierge_view = None
        html = _render_overview(state, readiness, action, cfg, stylesheet, concierge_view)
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
        from .telemetry import EV_STEP_ENTERED, emit

        emit(EV_STEP_ENTERED, step=key)
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
        from .telemetry import EV_PREVIEW_BUILT, emit

        emit(EV_PREVIEW_BUILT, value_path=value_path)
        return JSONResponse({"ok": True, "preview": plan.preview()})

    @app.post("/capture/apply")
    def capture_apply(
        value_path: str = Form(...),
        value: str = Form(...),
        csrf: str = Form(...),
    ) -> JSONResponse:
        # GE-M5 cloud read-only gate (FR-GE-8) via the M1 seam: cloud never writes — deferred to OQ-GE-7.
        if not _cloud_capability("capture").allowed:
            return _cloud_deferred("capture")
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
        from .telemetry import EV_CAPTURE_FAILED, EV_GAP_CLOSED, emit, kickoff_span

        with kickoff_span("kickoff.capture", value_path=value_path):
            try:
                plan = build_capture_plan(root, value_path, value, config=cfg)
                apply_capture(root, plan)  # emits field_captured on success
            except CaptureError as exc:
                emit(EV_CAPTURE_FAILED, value_path=value_path, code=exc.code)
                status = 409 if exc.code == CaptureCode.STALE_FILE else 400
                return _capture_error(exc, http_status=status)
            # Post-write refresh (R1-S10): re-run extraction so the badge flips immediately.
            state = load_state(root)
            fs = next((f for f in state.fields if f.value_path == plan.value_path), None)
            if fs is not None and fs.attention == "ok":
                emit(EV_GAP_CLOSED, value_path=plan.value_path)
            return JSONResponse(
                {
                    "ok": True,
                    "code": CaptureCode.OK,
                    "value_path": plan.value_path,
                    "applied": plan.preview(),
                    "refreshed_status": fs.attention if fs else None,
                }
            )

    # --- Template download (Welcome Mat 2.0, FR-WM2-1..4) ---------------------------------------

    from ..concierge.writes import (
        VALID_POSTURES,
        get_template_entry,
        kickoff_template_manifest,
        render_template_content,
    )

    @app.get("/templates", response_class=HTMLResponse)
    def templates_index(posture: str = "prototype") -> HTMLResponse:
        # The index is lenient (clamp an odd posture); the download routes below are strict.
        sel = posture if posture in VALID_POSTURES else "prototype"
        return HTMLResponse(_render_templates(kickoff_template_manifest(), sel, stylesheet))

    @app.get("/templates/file/{key}")
    def template_file(key: str, posture: str = "prototype") -> Response:
        # `key` is a single path segment (no slashes); an unknown/encoded key simply misses the closed
        # set → typed 404 (NR-3 key-closure). `posture` is validated strictly (R4-S7).
        from .telemetry import EV_TEMPLATE_DOWNLOADED, emit

        if posture not in VALID_POSTURES:
            return JSONResponse(
                {"ok": False, "code": "posture_invalid",
                 "message": f"posture must be one of {list(VALID_POSTURES)}"},
                status_code=400,
            )
        entry = get_template_entry(key)
        if entry is None:
            return JSONResponse(
                {"ok": False, "code": "unknown_template", "message": "no such template key"},
                status_code=404,
            )
        body = render_template_content(entry, posture).encode("utf-8")
        filename = entry.dest.rsplit("/", 1)[-1]
        emit(EV_TEMPLATE_DOWNLOADED, key=entry.key, group=entry.group, posture=posture)
        return Response(
            body,
            media_type=_template_media_type(entry.dest),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/templates/bundle.zip")
    def template_bundle(posture: str = "prototype", with_authoring: bool = True) -> Response:
        import io
        import zipfile

        from .telemetry import EV_TEMPLATE_BUNDLE_DOWNLOADED, emit

        if posture not in VALID_POSTURES:
            return JSONResponse(
                {"ok": False, "code": "posture_invalid",
                 "message": f"posture must be one of {list(VALID_POSTURES)}"},
                status_code=400,
            )
        entries = [e for e in kickoff_template_manifest()
                   if with_authoring or e.group == "package"]
        # Resolve content + enforce the uncompressed-bytes ceiling BEFORE building (FR-WM2-3): fail
        # closed with 413, never stream a partial archive.
        members = []
        total = 0
        for e in entries:
            content = render_template_content(e, posture).encode("utf-8")
            total += len(content)
            if total > _BUNDLE_MAX_UNCOMPRESSED_BYTES:
                return JSONResponse(
                    {"ok": False, "code": "bundle_too_large",
                     "message": "template bundle exceeds the size ceiling"},
                    status_code=413,
                )
            members.append((e.dest, content))  # dest is accessor-validated safe-relative (zip-slip)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dest, content in members:
                zf.writestr(dest, content)
        emit(EV_TEMPLATE_BUNDLE_DOWNLOADED, count=len(members), posture=posture,
             with_authoring=with_authoring)
        return Response(
            buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="kickoff-templates.zip"'},
        )

    # --- Concierge mode (M-CM3) -----------------------------------------------------------------

    from ..concierge.writes import build_friction_entry, build_instantiate_plan
    from .concierge_apply import (
        ConciergeInputError,
        ConciergeWriteCode,
        apply_concierge_plan,
        validate_friction,
        validate_posture,
    )
    from .concierge_view import build_concierge_view

    def _concierge_write_gate(host: Optional[str], csrf: str, now: float):
        """Shared gate for Concierge write POSTs: cloud, mode, loopback Host, CSRF, rate-limit."""
        if not _cloud_capability("concierge-write").allowed:  # GE-M5 via the seam — deferred (OQ-GE-7)
            return _cloud_deferred()
        if mode in ("preview", "inspect"):
            return JSONResponse({"ok": False, "code": "preview_only",
                                 "message": f"mode {mode!r} is read/preview only"}, status_code=403)
        if not _host_ok(host):
            return JSONResponse({"ok": False, "code": "forbidden_host",
                                 "message": "request Host is not a loopback address"}, status_code=403)
        if not sessions.valid(csrf, now):
            return JSONResponse({"ok": False, "code": "session_expired",
                                 "message": "invalid or expired token"}, status_code=403)
        if not sessions.rate_ok(csrf, now):
            return JSONResponse({"ok": False, "code": "rate_limited",
                                 "message": "too many writes; slow down"}, status_code=429)
        return None

    @app.get("/concierge", response_class=HTMLResponse)
    def concierge() -> HTMLResponse:
        from .telemetry import EV_SURVEY_VIEWED, emit

        view = build_concierge_view(root)
        emit(EV_SURVEY_VIEWED)
        token = sessions.issue(clock())
        issued = {
            "instantiate": intents.issue("instantiate", _plan_digest(build_instantiate_plan(root))),
            "friction": intents.issue("friction", "friction"),
        }
        resp = HTMLResponse(_render_concierge(view, token, issued, stylesheet),
                            headers=dict(_FRAME_DENY_HEADERS))
        resp.set_cookie("kickoff_csrf", token, httponly=True, samesite="strict")
        return resp

    @app.get("/concierge.json")
    def concierge_json() -> JSONResponse:
        # Shared view-model payload (parity oracle; the TUI renders the same dict).
        return JSONResponse(build_concierge_view(root), headers=dict(_FRAME_DENY_HEADERS))

    @app.get("/guided", response_class=HTMLResponse)
    def guided() -> HTMLResponse:
        # GE-M4 served leg — read/preview-only render of the ONE guided view-model (Orient → Guide →
        # Deepen, incl. the GE-M3b halt/cost states). Degrades to an error page if the kernel `assess`
        # cannot read the project; never 500s the surface.
        from .concierge_view import build_guided_view

        try:
            view = build_guided_view(root, load_deepen=True)
        except Exception as exc:
            return HTMLResponse(
                _page("Guided kickoff", f"<h1>Guided kickoff</h1><p>could not read project: "
                                        f"{_esc(exc)}</p>", stylesheet),
                status_code=200, headers=dict(_FRAME_DENY_HEADERS),
            )
        return HTMLResponse(_render_guided(view, stylesheet), headers=dict(_FRAME_DENY_HEADERS))

    @app.get("/guided.json")
    def guided_json() -> JSONResponse:
        # Same guided view-model payload the CLI `kickoff guided --json` emits and the TUI renders.
        from .concierge_view import build_guided_view

        try:
            view = build_guided_view(root, load_deepen=True)
        except Exception as exc:
            return JSONResponse({"ok": False, "code": "assess_failed", "message": str(exc)},
                                status_code=400, headers=dict(_FRAME_DENY_HEADERS))
        return JSONResponse(view, headers=dict(_FRAME_DENY_HEADERS))

    @app.get("/audience.json")
    def audience_json() -> JSONResponse:
        # FR-14/FR-19: the resolved audience + its disclosure tier + the selectable choices. Read-only.
        from ..concierge.audience import KickoffAudience, disclosure_tier, resolve_audience_preference

        res = resolve_audience_preference(root)
        return JSONResponse(
            {"audience": res.value.value, "source": res.source, "tier": disclosure_tier(res.value),
             "choices": [a.value for a in KickoffAudience]},
            headers=dict(_FRAME_DENY_HEADERS),
        )

    @app.post("/audience/set")
    def audience_set(audience: str = Form(...), csrf: str = Form(...),
                     host: Optional[str] = Header(default=None)) -> JSONResponse:
        """FR-19: the web audience selector. Persists via the **same** canonical
        ``set_audience_preference`` the CLI uses (NOT a second write path), behind the shared write
        gate (cloud read-only / feature-mode / loopback-Host / CSRF / rate-limit). Writes ONLY the
        preference — no pre-pass (A-OQ10); the audience takes effect at the next walk-start."""
        gate = _concierge_write_gate(host, csrf, clock())
        if gate is not None:
            return gate
        from ..concierge.audience import set_audience_preference

        try:
            result = set_audience_preference(audience, project_root=root, scope="project")
        except ValueError as exc:
            return JSONResponse({"ok": False, "code": "bad_audience", "message": str(exc)},
                                status_code=400, headers=dict(_FRAME_DENY_HEADERS))
        except OSError as exc:   # a write/permission failure must not 500 the surface
            return JSONResponse({"ok": False, "code": "write_failed", "message": str(exc)},
                                status_code=500, headers=dict(_FRAME_DENY_HEADERS))
        return JSONResponse({"ok": True, "audience": result.value.value, "scope": result.scope,
                             "target": result.target}, headers=dict(_FRAME_DENY_HEADERS))

    @app.get("/red-carpet.json")
    def red_carpet_json() -> JSONResponse:
        # The Red Carpet staged build map (FR-RCT-2, OQ-4) — read-only, $0; the chat-page stage rail
        # fetches this. Same payload as `startd8 kickoff red-carpet --json` and the agent's tool.
        from .red_carpet import build_red_carpet_state

        return JSONResponse(build_red_carpet_state(root).to_dict(), headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/instantiate/preview")
    def instantiate_preview(posture: str = Form("prototype")) -> JSONResponse:
        try:
            validate_posture(posture)
        except ConciergeInputError as exc:
            return JSONResponse({"ok": False, "code": exc.code, "message": str(exc)}, status_code=400)
        plan = build_instantiate_plan(root, posture)
        # Preview only — no write; summarize per-file path/status/bytes (R2-S1).
        summary = [{"path": w["path"], "status": w["status"], "bytes": w["bytes"]}
                   for w in plan["writes"]]
        return JSONResponse({"ok": True, "action": "instantiate-kickoff", "posture": posture,
                             "writes": summary, "warnings": plan.get("warnings", [])},
                            headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/instantiate")
    def instantiate(posture: str = Form("prototype"), csrf: str = Form(...),
                    intent: str = Form(...), host: Optional[str] = Header(default=None)) -> JSONResponse:
        from .telemetry import EV_CONCIERGE_WRITE_REFUSED, EV_KICKOFF_INSTANTIATED, emit, kickoff_span

        gate = _concierge_write_gate(host, csrf, clock())
        if gate is not None:
            return gate
        try:
            validate_posture(posture)
        except ConciergeInputError as exc:
            return JSONResponse({"ok": False, "code": exc.code, "message": str(exc)}, status_code=400)
        plan = build_instantiate_plan(root, posture)
        if not intents.consume(intent, "instantiate", _plan_digest(plan)):
            return JSONResponse({"ok": False, "code": "replay",
                                 "message": "intent already used or mismatched; reload Concierge"},
                                status_code=409, headers=dict(_FRAME_DENY_HEADERS))
        with kickoff_span("kickoff.concierge.instantiate", posture=posture):
            result = apply_concierge_plan(root, plan)
        # Post-apply reconciliation (R3-S2): the refreshed package state.
        refreshed = build_concierge_view(root)["instantiate_offer"]
        if result.ok and result.wrote_anything:
            emit(EV_KICKOFF_INSTANTIATED, posture=posture, code=result.code,
                 written_count=len(result.written))
        elif not result.ok:
            emit(EV_CONCIERGE_WRITE_REFUSED, action="instantiate", code=result.code)
        body = {"ok": result.ok, **result.to_dict(), "package_state": refreshed["package_state"]}
        status = 200 if result.ok else (409 if result.code == ConciergeWriteCode.WRITE_BLOCKED else 400)
        return JSONResponse(body, status_code=status, headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/friction")
    def friction(friction: str = Form(""), what_happened: str = Form(""),
                 implication: str = Form(""), csrf: str = Form(...),
                 intent: str = Form(...), host: Optional[str] = Header(default=None)) -> JSONResponse:
        # Fields default to "" so blank input reaches validate_friction (typed 400) rather than a
        # bare FastAPI 422 — the typed-validation contract (R2-F5).
        import uuid
        from datetime import datetime, timezone

        from .telemetry import EV_CONCIERGE_WRITE_REFUSED, EV_FRICTION_LOGGED, emit

        gate = _concierge_write_gate(host, csrf, clock())
        if gate is not None:
            return gate
        try:
            validate_friction(friction, what_happened, implication)
        except ConciergeInputError as exc:
            return JSONResponse({"ok": False, "code": exc.code, "message": str(exc)}, status_code=400)
        if not intents.consume(intent, "friction", "friction"):
            return JSONResponse({"ok": False, "code": "replay",
                                 "message": "intent already used; reload Concierge"},
                                status_code=409, headers=dict(_FRAME_DENY_HEADERS))
        # NR-CM-B: the SURFACE stamps the timestamp INTO the builder (it bakes ts into append_text).
        plan = build_friction_entry(
            root, friction=friction, what_happened=what_happened, implication=implication,
            entry_id=uuid.uuid4().hex, timestamp=datetime.now(timezone.utc).isoformat(),
        )
        result = apply_concierge_plan(root, plan)
        if result.ok:
            emit(EV_FRICTION_LOGGED, code=result.code)  # no free-text/paths (R2-F4 privacy)
        else:
            emit(EV_CONCIERGE_WRITE_REFUSED, action="friction", code=result.code)
        status = 200 if result.ok else (409 if result.code == ConciergeWriteCode.WRITE_BLOCKED else 400)
        return JSONResponse({"ok": result.ok, **result.to_dict()}, status_code=status,
                            headers=dict(_FRAME_DENY_HEADERS))

    # --- agentic chat panel (web agentic surface) ----------------------------------------------

    def _chat_unavailable_cloud() -> HTMLResponse:
        # GE-M5 (FR-GE-8): the agentic chat spends LLM tokens — disabled on cloud unless a valid grant +
        # trust chain (FR-14) authorizes it. Byte-identical to the prior cloud-unavailable view.
        return HTMLResponse(
            _page("Concierge — chat",
                  "<p><a href='/concierge'>← Concierge</a></p><h1>Chat unavailable on cloud</h1>"
                  "<p>This is a cloud read/preview-only surface — the conversational Concierge "
                  "and the paid facilitation panel are disabled (OQ-GE-7). Use a local install "
                  "to author, or download the kickoff templates and write locally.</p>",
                  stylesheet),
            headers=dict(_FRAME_DENY_HEADERS))

    @app.get("/concierge/chat", response_class=HTMLResponse)
    def chat_page(x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
                  origin: Optional[str] = Header(default=None)) -> HTMLResponse:
        if cloud and _grant_store is None:
            return _chat_unavailable_cloud()   # cloud + no grant store → strict (== today)
        if chat_factory is None:
            return HTMLResponse(
                _page("Concierge — chat",
                      "<p><a href='/concierge'>← Concierge</a></p><h1>Agentic chat not enabled</h1>"
                      "<p>Start the server with an agent (e.g. <code>startd8 kickoff start --agent "
                      "anthropic:claude-sonnet-4-6</code>) to enable the conversational Concierge.</p>",
                      stylesheet),
                headers=dict(_FRAME_DENY_HEADERS))
        if mode in ("preview", "inspect"):
            # FR-WM2-8a: chat spends LLM tokens, so it is disabled in read/preview serve modes
            # (parity with the capture/Concierge write refusal). The spend path below also refuses.
            return HTMLResponse(
                _page("Concierge — chat",
                      "<p><a href='/concierge'>← Concierge</a></p><h1>Chat disabled in read/preview mode</h1>"
                      f"<p>This server runs in <code>{_esc(mode)}</code> mode — the conversational "
                      "Concierge spends LLM tokens and is disabled. Serve in write mode to enable it.</p>",
                      stylesheet),
                headers=dict(_FRAME_DENY_HEADERS))
        _grant_binding = None
        if cloud:
            # Grant-capable cloud build: creating a session requires the full FR-14 trust chain and
            # CONSUMES one use (FR-15). Checked here (session creation / pre-message surface, R1-S7) so no
            # live chat surface exists before a grant is validated. A missing factor → unavailable, no
            # session, no use spent (the trust chain short-circuits before consume on api-key/Origin).
            from .cloud_grant import GrantTarget
            _decision = _cloud_capability("chat-write", req_api_key=x_api_key, req_origin=origin)
            if not _decision.allowed:
                return _chat_unavailable_cloud()
            # Bind the consumed grant to the session so per-turn actions REVALIDATE it (M3, no re-consume).
            _grant_binding = (_decision.grant_id,
                              GrantTarget(_deployment_id, _project_id, "chat-write"))
        now = clock()
        # FR-WM2-5a: the chat SESSION id and the CSRF/write token are SEPARATE secrets in SEPARATE
        # httponly cookies. The chat sid keys _ChatStore (+ message rate); csrf gates the write path.
        chat_sid = sessions.issue(now)
        csrf = sessions.issue(now)
        chats.put(chat_sid, chat_factory())
        if _grant_binding is not None:
            _session_grants[chat_sid] = _grant_binding
        resp = HTMLResponse(_render_chat_page(csrf, stylesheet), headers=dict(_FRAME_DENY_HEADERS))
        resp.set_cookie("kickoff_chat", chat_sid, httponly=True, samesite="strict")
        resp.set_cookie("kickoff_csrf", csrf, httponly=True, samesite="strict")
        return resp

    # FR-E12 — the human door. Only registered on a grant-capable cloud build (byte-identical route
    # table otherwise). Lets a human CLICK a one-time link to open the granted chat without crafting the
    # X-API-Key header the programmatic path needs: possession of the link is the authorization proof.
    if cloud and _grant_store is not None:
        def _redeem_host_ok(host_header: Optional[str]) -> bool:
            """FR-5: confine redemption to a configured/loopback host (a leaked link can't be redeemed
            against an unexpected host)."""
            if _host_ok(host_header):                    # loopback always allowed (local cloud)
                return True
            if not host_header:
                return False
            from urllib.parse import urlsplit
            req = host_header.split(":", 1)[0].strip().lower()
            return any((urlsplit(o).hostname or "").lower() == req for o in _cloud_origins)

        def _link_invalid_page() -> HTMLResponse:
            """FR-6: ONE generic response for every failure — no oracle distinguishing unknown vs used
            vs expired vs wrong-host."""
            return HTMLResponse(
                _page("Kickoff — link",
                      "<h1>This link is invalid, expired, or already used</h1>"
                      "<p>Magic links are one-time and short-lived. Ask your operator for a fresh "
                      "link (<code>startd8 cloud-grant issue --with-link</code>).</p>", stylesheet),
                status_code=403, headers=dict(_FRAME_DENY_HEADERS))

        @app.get("/kickoff/enter", response_class=HTMLResponse)
        def kickoff_enter(t: str = Query(default=""),
                          host: Optional[str] = Header(default=None)) -> HTMLResponse:
            if chat_factory is None or mode in ("preview", "inspect"):
                return _link_invalid_page()              # nothing to open → same generic page (no oracle)
            if not _redeem_host_ok(host):
                return _link_invalid_page()
            from .cloud_grant import GrantTarget
            target = GrantTarget(_deployment_id, _project_id, "chat-write")
            decision = _grant_store.redeem_link(t, target, now=_grant_clock())
            if not decision.allowed:
                return _link_invalid_page()
            # Mint the SAME session chat_page mints — but on the human's behalf (they never sent api-key).
            # The link burn + grant consume already happened atomically; the token in the URL is now dead.
            now = clock()
            chat_sid = sessions.issue(now)
            csrf = sessions.issue(now)
            chats.put(chat_sid, chat_factory())
            _session_grants[chat_sid] = (decision.grant_id, target)   # per-turn REVALIDATES (no re-consume)
            resp = HTMLResponse(_render_chat_page(csrf, stylesheet), headers=dict(_FRAME_DENY_HEADERS))
            resp.set_cookie("kickoff_chat", chat_sid, httponly=True, samesite="strict")
            resp.set_cookie("kickoff_csrf", csrf, httponly=True, samesite="strict")
            return resp

    def _chat_for(kickoff_chat: Optional[str]):
        """Resolve the live chat from the `kickoff_chat` cookie (FR-WM2-5a). A missing/unknown cookie
        is an expired session — a bare CSRF token can never substitute for it."""
        return chats.get(kickoff_chat or "")

    def _chat_refused(code: str, status: int) -> JSONResponse:
        from .telemetry import EV_CHAT_REFUSED, emit
        emit(EV_CHAT_REFUSED, code=code)   # bounded code; never the message text (FR-WM2-14a)
        return JSONResponse({"ok": False, "code": code}, status_code=status,
                            headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/chat/message")
    async def chat_message(message: str = Form(...), host: Optional[str] = Header(default=None),
                           origin: Optional[str] = Header(default=None),
                           kickoff_chat: Optional[str] = Cookie(default=None)) -> JSONResponse:
        from .telemetry import EV_CHAT_TURN, emit, kickoff_span
        # Cloud posture (M3): a turn is permitted only by REVALIDATING the session's grant — no re-consume
        # (R1-S9), so a session created just before expiry/revocation is denied HERE on its next action.
        # The loopback-Host check is a LOCAL trust factor; on cloud the substrate is grant + api-key
        # (APIKeyMiddleware) + Origin (revalidate), so `_host_ok` is bypassed for the cloud path (FR-14).
        if cloud:
            if not _cloud_revalidate(kickoff_chat, origin):
                return _cloud_deferred("chat")
        if mode in ("preview", "inspect"):           # FR-WM2-8a — never spend in read/preview modes
            return _chat_refused("preview_only", 403)
        if not cloud and not _host_ok(host):
            return JSONResponse({"ok": False, "code": "forbidden_host"}, status_code=403)
        if len(message) > _MAX_CHAT_MESSAGE_CHARS:   # FR-WM2-5b — reject before any provider call
            return _chat_refused("message_too_long", 400)
        chat = _chat_for(kickoff_chat)
        if chat is None:
            return _chat_refused("chat_session_expired", 403)
        if not sessions.rate_ok(kickoff_chat, clock()):   # bound LLM-spend turns (per chat session)
            return _chat_refused("rate_limited", 429)
        # FR-WM2-5c — one in-flight turn per session; a concurrent request fails fast (never interleaves
        # AgenticSession history). Prune unlocked locks so the registry stays bounded.
        if len(chat_locks) > _ChatStore._MAX * 2:
            for k in [k for k, lk in chat_locks.items() if not lk.locked()]:
                chat_locks.pop(k, None)
        lock = chat_locks.setdefault(kickoff_chat, asyncio.Lock())
        if lock.locked():
            return _chat_refused("chat_busy", 429)
        from .telemetry import EV_CHAT_REFUSED
        async with lock:
            # R3-S8: wrap the whole turn so the AgenticSession `agentic.session`/`agentic.turn` child
            # spans AND the funnel events (chat_turn / chat_refused) nest under one kickoff span.
            with kickoff_span("kickoff.concierge.chat_turn"):
                try:
                    result = await chat.ask(message)
                except Exception:                    # FR-WM2-8c — sanitized; a provider fault never 500s
                    return _chat_refused("chat_error", 200)
                stop_code = _CHAT_STOP_CODE.get(result.stop_reason)   # FR-WM2-8b
                if stop_code is not None:
                    emit(EV_CHAT_REFUSED, code=stop_code, stop_reason=result.stop_reason)
                    return JSONResponse({"ok": False, "code": stop_code, "text": result.text,
                                         "cost": _chat_cost_block(chat, result)},
                                        status_code=200, headers=dict(_FRAME_DENY_HEADERS))
                proposals = [{"id": a.id, "kind": a.kind, "summary": a.summary()}
                             for a in chat.buffer.pending()]
                # Mirror (redacted) → cockpit. Locally: the FR-WM2-5d-softened opt-in. On cloud: allowed
                # only for a GRANT-authorized session (M3b) — the grant temporarily lifts the hosted-strict
                # no-disk posture for exactly this session; still redacted (FR-9), so no secret hits disk.
                if mirror_cockpit or (cloud and (kickoff_chat or "") in _session_grants):
                    _mirror_session_to_cockpit(root, chat)
                emit(EV_CHAT_TURN, turns=getattr(result, "turns", None),
                     tokens=getattr(result, "total_tokens", None),
                     cost_usd=getattr(result, "total_cost_usd", None),
                     stop_reason=result.stop_reason)
                return JSONResponse({"ok": True, "text": result.text,
                                     "cost": _chat_cost_block(chat, result),
                                     "proposals": proposals}, headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/chat/pending")
    def chat_pending(kickoff_chat: Optional[str] = Cookie(default=None)) -> JSONResponse:
        chat = _chat_for(kickoff_chat)
        proposals = ([{"id": a.id, "kind": a.kind, "summary": a.summary()}
                      for a in chat.buffer.pending()] if chat else [])
        return JSONResponse({"ok": True, "proposals": proposals}, headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/chat/confirm")
    def chat_confirm(proposal_id: str = Form(...), csrf: str = Form(...),
                     host: Optional[str] = Header(default=None),
                     origin: Optional[str] = Header(default=None),
                     kickoff_chat: Optional[str] = Cookie(default=None)) -> JSONResponse:
        from .proposals import apply_proposal
        from .telemetry import EV_PROPOSAL_CONFIRMED, emit
        # M3b: proposal-apply is a WRITE. On cloud it is permitted only by REVALIDATING the session's
        # grant (no re-consume, R1-S9); the loopback-Host + local-CSRF chain is replaced by grant +
        # api-key (APIKeyMiddleware) + Origin (FR-14). Local keeps the full _concierge_write_gate. The
        # apply below is UNCHANGED — the same `apply_proposal` safe-writer + validation (FR-16).
        if cloud:
            if not _cloud_revalidate(kickoff_chat, origin):
                return _cloud_deferred()
        else:
            gate = _concierge_write_gate(host, csrf, clock())   # csrf is distinct from the chat sid
            if gate is not None:
                return gate
        chat = _chat_for(kickoff_chat)
        if chat is None:
            return JSONResponse({"ok": False, "code": "chat_session_expired"}, status_code=403)
        action = next((a for a in chat.buffer.pending() if a.id == proposal_id), None)
        if action is None:
            return JSONResponse({"ok": False, "code": "no_such_proposal"}, status_code=404)
        outcome = apply_proposal(root, action, config=cfg)
        if not outcome.retriable:                 # pop on terminal success/failure; keep if retriable
            chat.buffer.pop(action.id)
        emit(EV_PROPOSAL_CONFIRMED, kind=outcome.kind, code=outcome.code)
        package_state = build_concierge_view(root)["instantiate_offer"]["package_state"]
        status = 200 if outcome.ok else (409 if outcome.retriable else 400)
        return JSONResponse({"ok": outcome.ok, "code": outcome.code, "detail": outcome.detail,
                             "retriable": outcome.retriable, "package_state": package_state},
                            status_code=status, headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/chat/discard")
    def chat_discard(proposal_id: str = Form(...), csrf: str = Form(...),
                     kickoff_chat: Optional[str] = Cookie(default=None)) -> JSONResponse:
        from .telemetry import EV_PROPOSAL_DISCARDED, emit
        if not sessions.valid(csrf, clock()):     # a discard mutates server state → CSRF-protected
            return JSONResponse({"ok": False, "code": "session_expired"}, status_code=403)
        chat = _chat_for(kickoff_chat)
        if chat is not None:
            kind = next((a.kind for a in chat.buffer.pending() if a.id == proposal_id), "?")
            chat.buffer.pop(proposal_id)
            emit(EV_PROPOSAL_DISCARDED, kind=kind)
        return JSONResponse({"ok": True}, headers=dict(_FRAME_DENY_HEADERS))

    @app.post("/concierge/chat/reset")
    def chat_reset(csrf: str = Form(...),
                   kickoff_chat: Optional[str] = Cookie(default=None)) -> JSONResponse:
        # R4-F6 — new conversation: destroy the current session's history and mint a fresh one. $0,
        # no provider call, no chat_turn event. CSRF-protected (it mutates server state).
        # reset MINTS A NEW session, so on cloud it is INTENTIONALLY denied even under a grant — allowing
        # it would create an un-metered session that never traversed the FR-14 trust chain / consumed a
        # use. A grant user opens a fresh conversation via `/concierge/chat` (which consumes a use).
        if not _cloud_capability("chat").allowed:  # cloud: reset denied by design (open a new session)
            return _cloud_deferred("chat")
        if chat_factory is None:
            return JSONResponse({"ok": False, "code": "chat_disabled"}, status_code=409,
                                headers=dict(_FRAME_DENY_HEADERS))
        if not sessions.valid(csrf, clock()):
            return JSONResponse({"ok": False, "code": "session_expired"}, status_code=403,
                                headers=dict(_FRAME_DENY_HEADERS))
        chats.discard(kickoff_chat)               # drop + wipe old history (FR-WM2-5d)
        chat_locks.pop(kickoff_chat or "", None)
        new_sid = sessions.issue(clock())
        chats.put(new_sid, chat_factory())
        resp = JSONResponse({"ok": True}, headers=dict(_FRAME_DENY_HEADERS))
        resp.set_cookie("kickoff_chat", new_sid, httponly=True, samesite="strict")
        return resp

    # GE-M5 — reuse the static server/auth.py X-API-Key as the coarse cloud gate on mutation (POST)
    # requests (NOT a new tenancy model — OQ-GE-7). Cloud writes 501 regardless; this additionally
    # protects the read-only preview POSTs behind the shared key.
    if cloud and api_key:
        from ..server.auth import APIKeyMiddleware

        app.add_middleware(APIKeyMiddleware, api_key=api_key)

    return app
