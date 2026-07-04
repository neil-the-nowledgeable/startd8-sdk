"""Interactive local-server mode for the consultation web view (FR-SRV / M1–M4).

OPT-IN (`startd8 consult web <id> --serve`). Turns the read-only static view into an interactive
follow-up surface: a **loopback-only** HTTP server executes follow-ups through the **same**
`ConsultationEngine` the CLI uses. This module is import-guarded — `starlette`/`uvicorn` are the
`startd8[server]` extras; absence degrades to the static file (FR-SRV-8).

Security model (WEB_UI_SERVE_REQUIREMENTS.md v0.4, FR-SRV-4) — all enforced here:
- **(a)** loopback asserted on the *bound socket address* (not a string blacklist); IPv6 dual-stack off.
- **(b)** per-run token (`secrets`), **constant-time** compare, validated **before** any session work;
  never in the access log; page strips it from the URL; `Referrer-Policy: no-referrer`.
- **(c)** `Host` must be `127.0.0.1[:port]`; state-changing POST rejected unless `Origin` == our origin
  (missing/`null` Origin → rejected).
- **(d)** single session; `GET /` and `GET /session` are token-gated (no session content without the token).
- **(e)** strict **CSP** (per-response nonce; no `unsafe-inline`) + `connect-src 'self'`; model markdown is
  escaped/sanitized by the client renderer — a page-XSS cannot exfiltrate the spend-capable token.
- **(f)** uniform, content-free error bodies (no existence oracle).
- **(g)** any `Upgrade`/WebSocket request is rejected at ASGI scope.
Cost guard (FR-SRV-5): turn cap + call ceiling + single-use nonce (replay), incremented **before** the
paid call under an `asyncio.Lock`. Cross-process second-server refusal via a lockfile (FR-SRV-6).
"""

from __future__ import annotations

import asyncio
import ipaddress
import secrets
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..agents.base import BaseAgent
from ..logging_config import get_logger
from .engine import ConsultationEngine
from .models import ConsultationSession
from .store import ConsultationStore
from .view import render_html

logger = get_logger(__name__)

try:  # soft dependency (FR-SRV-8)
    from starlette.applications import Starlette
    from starlette.middleware import Middleware
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
    from starlette.routing import Route
    from starlette.datastructures import Headers, MutableHeaders
    _SERVER_OK = True
except ImportError:  # pragma: no cover - exercised only where extras are absent
    Starlette = None  # type: ignore[assignment,misc]
    _SERVER_OK = False


class ServerExtrasMissing(RuntimeError):
    """Raised when starlette/uvicorn (`startd8[server]`) are not installed."""


class SessionAlreadyServed(RuntimeError):
    """Raised when another `--serve` already owns this session (cross-process guard, FR-SRV-6)."""


# script-src is the security-critical directive (a nonce blocks injected <script> + inline handlers →
# an XSS cannot read/exfiltrate the spend-capable token). style-src stays 'unsafe-inline' because the
# template uses inline style attributes / JS-set styles, and injected CSS cannot steal the token;
# connect-src 'self' blocks exfiltration to a foreign host. (FR-SRV-4e)
CSP_TEMPLATE = (
    "default-src 'none'; script-src 'nonce-{n}'; style-src 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


# ── loopback socket (FR-SRV-1/4a, R2-F5) ──────────────────────────────────────
def open_loopback_socket(host: str = "127.0.0.1", port: int = 0) -> "socket.socket":
    """Bind a loopback TCP socket and **assert** the bound address is loopback.

    Refuses non-loopback hosts up front, sets **no** `SO_REUSEADDR`/`SO_REUSEPORT`, disables IPv6
    dual-stack, binds, then verifies `getsockname()` is in `127.0.0.0/8`/`::1` (positive assertion,
    not a string blacklist). Order is bind → getsockname; the caller mints/prints only after this
    returns (FR-SRV-1).
    """
    try:
        addr = ipaddress.ip_address(host)
    except ValueError as e:
        raise ValueError(f"refusing non-numeric bind host {host!r} (loopback only)") from e
    if not addr.is_loopback:
        raise ValueError(f"refusing non-loopback bind address {host!r}")

    family = socket.AF_INET6 if addr.version == 6 else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    # Deliberately NO SO_REUSEADDR/SO_REUSEPORT (R2-F5): don't let another local process share/pre-own.
    if family == socket.AF_INET6:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    try:
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    bound_host = sock.getsockname()[0]
    if not ipaddress.ip_address(bound_host).is_loopback:  # defense in depth
        sock.close()
        raise ValueError(f"bound address {bound_host!r} is not loopback — refusing")
    sock.listen(16)
    return sock


# ── server state ──────────────────────────────────────────────────────────────
@dataclass
class ServeState:
    session_id: str
    store: ConsultationStore
    roster: "dict[str, BaseAgent]"
    token: str
    origin: str                       # e.g. "http://127.0.0.1:54321"
    port: int
    max_turns: int = 20
    max_calls: int = 60               # hard fan-out/spend ceiling (model-calls)
    reply_timeout_s: float = 180.0
    engine: ConsultationEngine = field(init=False)
    lock: "asyncio.Lock" = field(init=False)
    _turns: int = 0
    _calls: int = 0
    _nonces: set = field(default_factory=set)

    def __post_init__(self):
        self.engine = ConsultationEngine(self.store)
        self.lock = asyncio.Lock()

    def mint_nonce(self) -> str:
        n = secrets.token_urlsafe(12)
        self._nonces.add(n)
        return n


# ── security middleware (FR-SRV-4) ─────────────────────────────────────────────
def _uniform(status: int):
    """Content-free, id-independent error response (FR-SRV-4f — no existence oracle)."""
    return PlainTextResponse("", status_code=status)


def _token_ok(supplied: Optional[str], expected: str) -> bool:
    if not supplied:
        return False
    return secrets.compare_digest(supplied, expected)  # constant-time (R1-F10)


def _host_ok(host: str, port: int) -> bool:
    # Host must be exactly 127.0.0.1[:port] (FR-SRV-4c) — reject localhost/evil.com.
    return host in (f"127.0.0.1:{port}", "127.0.0.1")


class _SecurityMiddleware:
    """Pure-ASGI guard: token + Host/Origin + upgrade-reject + security headers (runs for all scopes)."""

    def __init__(self, app, state: ServeState):
        self.app = app
        self.state = state

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":  # FR-SRV-4g: no upgrade paths in v1
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)  # lifespan etc.
            return

        headers = Headers(scope=scope)
        method = scope["method"]

        # (c) Host allowlist + (g) Upgrade reject — before anything else.
        if not _host_ok(headers.get("host", ""), self.state.port):
            return await _uniform(403)(scope, receive, send)
        if headers.get("upgrade"):
            return await _uniform(400)(scope, receive, send)

        # (b) token — validated BEFORE any session/roster work (no oracle). Query on GET nav; header else.
        supplied = headers.get("x-consult-token") or _query_token(scope)
        if not _token_ok(supplied, self.state.token):
            return await _uniform(401)(scope, receive, send)

        # (c) Origin fail-closed for state-changing POST (missing/null rejected).
        if method == "POST":
            origin = headers.get("origin")
            if not origin or origin != self.state.origin:
                return await _uniform(403)(scope, receive, send)

        # (e) per-response CSP nonce; route reads it from scope to stamp inline tags.
        nonce = secrets.token_urlsafe(16)
        scope["csp_nonce"] = nonce

        async def send_wrap(message):
            if message["type"] == "http.response.start":
                mh = MutableHeaders(raw=message.setdefault("headers", []))
                mh["content-security-policy"] = CSP_TEMPLATE.format(n=nonce)
                mh["referrer-policy"] = "no-referrer"
                mh["x-content-type-options"] = "nosniff"
                mh["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_wrap)


def _query_token(scope) -> Optional[str]:
    qs = scope.get("query_string", b"").decode()
    for part in qs.split("&"):
        if part.startswith("t="):
            return part[2:]
    return None


# ── routes ──────────────────────────────────────────────────────────────────
def _session_payload_json(state: ServeState):
    from .view import _session_payload

    return _session_payload(state.store.load(state.session_id))


def build_app(state: ServeState):
    """Construct the single-session Starlette app (guarded by `_SecurityMiddleware`)."""
    if not _SERVER_OK:
        raise ServerExtrasMissing("starlette is required: pip install startd8[server]")

    async def get_index(request: "Request"):
        session = state.store.load(state.session_id)
        nonce = request.scope.get("csp_nonce", "")
        serve_cfg = {
            "token": state.token,
            "reply_url": "/reply",
            "session_url": "/session",
            "nonce": state.mint_nonce(),
            "max_turns": state.max_turns,
            "turns_used": state._turns,
        }
        html = render_html(session, serve=serve_cfg, csp_nonce=nonce)
        return HTMLResponse(html)

    async def get_session(request: "Request"):
        return JSONResponse(_session_payload_json(state))

    async def post_reply(request: "Request"):
        try:
            body = await request.json()
        except Exception:
            return _uniform(400)
        prompt = (body.get("prompt") or "").strip()
        target = body.get("target") or "all"
        nonce = body.get("nonce")
        if not prompt:
            return JSONResponse({"error": "empty prompt"}, status_code=400)

        # Everything cost-relevant happens atomically under the lock (FR-SRV-5/6).
        async with state.lock:
            # (replay) single-use nonce
            if nonce not in state._nonces:
                return JSONResponse({"error": "stale request"}, status_code=409)
            state._nonces.discard(nonce)

            targets = list(state.roster) if target == "all" else [target]
            if target != "all" and target not in state.roster:
                return JSONResponse({"error": "unknown target"}, status_code=400)

            # caps checked + incremented BEFORE the paid call (R1-S4)
            if state._turns >= state.max_turns:
                return JSONResponse({"error": "turn cap reached"}, status_code=429)
            if state._calls + len(targets) > state.max_calls:
                return JSONResponse({"error": "spend ceiling reached"}, status_code=402)
            state._turns += 1
            state._calls += len(targets)

            session = state.store.load(state.session_id)
            try:
                await asyncio.wait_for(
                    state.engine.follow_up(session, state.roster, prompt, target),
                    timeout=state.reply_timeout_s,
                )
            except asyncio.TimeoutError:
                return JSONResponse({"error": "model call timed out"}, status_code=504)

        from .view import _session_payload

        return JSONResponse({"session": _session_payload(session), "next_nonce": state.mint_nonce()})

    routes = [
        Route("/", get_index),
        Route("/session", get_session),
        Route("/reply", post_reply, methods=["POST"]),
    ]
    return Starlette(routes=routes, middleware=[Middleware(_SecurityMiddleware, state=state)])


# ── cross-process lock (FR-SRV-6) ─────────────────────────────────────────────
def _pid_alive(pid: int) -> bool:
    import os

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # exists but not ours
        return True
    return True


def acquire_serve_lock(store: ConsultationStore, session_id: str) -> Path:
    """Refuse a second **live** `--serve` on the same session; self-heal a stale (dead-PID) lock.

    The marker records the owner PID. If a marker exists but its PID is dead (hard kill / crash /
    parent death), it is reclaimed automatically — so a non-clean exit never permanently blocks
    future serves (the gap the live boot smoke exposed).
    """
    import os

    marker = store.session_dir(session_id) / ".serve.lock"
    if marker.exists():
        try:
            old_pid = int(marker.read_text().strip() or "0")
        except (ValueError, OSError):
            old_pid = 0
        if _pid_alive(old_pid):
            raise SessionAlreadyServed(
                f"session {session_id} is already being served by pid {old_pid} "
                f"(remove {marker} if you're sure it's stale)"
            )
        marker.unlink(missing_ok=True)  # stale → reclaim
    try:
        fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError as e:  # lost a race to another starting server
        raise SessionAlreadyServed(
            f"session {session_id} is already being served (remove {marker} if stale)"
        ) from e
    return marker


# ── orchestrated startup (FR-SRV-1/7/8) ───────────────────────────────────────
def run_serve(
    *,
    session_id: str,
    store: ConsultationStore,
    roster: "dict[str, BaseAgent]",
    port: int = 0,
    max_turns: int = 20,
    max_calls: int = 60,
    timeout: float = 180.0,
    open_browser: bool = False,
    emit=print,
) -> None:
    """Ordered, token-free-on-failure startup + blocking serve (FR-SRV-8).

    Sequence: [extras already imported] → acquire cross-process lock → **bind** (loopback, asserted)
    → **mint token** → print/open URL → run. A failure before the bind leaves no token minted, no
    port bound, no URL printed. Releases the lock + closes the socket on shutdown.
    """
    if not _SERVER_OK:
        raise ServerExtrasMissing("starlette + uvicorn required: pip install startd8[server]")
    import uvicorn

    marker = acquire_serve_lock(store, session_id)  # cross-process guard (before bind)
    sock = None
    try:
        sock = open_loopback_socket("127.0.0.1", port)   # bind first (R2-F5 order)
        actual_port = sock.getsockname()[1]
        token = secrets.token_urlsafe(32)                # mint only after a confirmed bind
        origin = f"http://127.0.0.1:{actual_port}"
        state = ServeState(
            session_id=session_id, store=store, roster=roster, token=token, origin=origin,
            port=actual_port, max_turns=max_turns, max_calls=max_calls, reply_timeout_s=timeout,
        )
        app = build_app(state)
        url = f"{origin}/?t={token}"

        if open_browser:
            import webbrowser
            webbrowser.open(url)
            emit(f"[serve] opened {origin}/  (token in the opened URL — not printed). Ctrl-C to stop.")
        else:
            emit(f"[serve] open this URL (contains a secret token — treat like a password):\n  {url}")
        emit(f"[serve] caps: max_turns={max_turns} max_calls={max_calls}. Ctrl-C to stop.")

        # access_log=False keeps the token-bearing GET / URL out of the access log (FR-SRV-4b).
        config = uvicorn.Config(app, log_level="warning", access_log=False)
        uvicorn.Server(config).run(sockets=[sock])
    finally:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        if sock is not None:
            sock.close()
