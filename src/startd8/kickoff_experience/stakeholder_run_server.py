"""Phase 2 M0 (HTTP shell) — the CLI-backed stakeholder-run endpoint.

A thin Starlette app over :mod:`stakeholder_run` (the fail-closed core). Never runs the LLM in
Grafana — the browser panel POSTs here (server-side, via the datasource proxy) and this process runs
the panel behind the guardrails.

Auth is **scoped to the deployment posture** (FR-2, local-posture split):
  * **Always on:** a constant-time **bearer token** (the endpoint refuses to start without one) + the
    fail-closed **budget ceiling** (the core's `ensure_blocking_budget`). `run_key` idempotency
    neutralizes replay double-charge.
  * **Local-trusted default (household):** token + budget + idempotency is enough. CSRF is N/A
    (header token, not a cookie; write originates server-side from the proxy); replay harm is covered.
  * **`strict=True` (untrusted/shared network):** additionally enforce an Origin allow-list + a replay
    nonce; prefer binding the docker-bridge IP over broad `0.0.0.0`.

Endpoints: ``POST /stakeholders/run`` (``{question, cap, dry_run, run_key, model?}``),
``GET /stakeholders/run/{session_id}``, ``GET /healthz`` (unauthenticated liveness). The Increment 3
panel-processing pipeline adds ``$0`` drive routes (same auth): ``POST /stakeholders/triage``,
``…/disposition``, ``…/serialize``, ``…/negotiate`` (an opt-in narrative pass spends its own
``max_cost_usd`` ceiling). The write-touching apply gate lands separately (M-apply).
"""

from __future__ import annotations

import hmac
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .stakeholder_run import (
    BudgetNotConfiguredError,
    RunKeyMismatchError,
    StakeholderRunError,
    cancel_run,
    dry_run,
    execute_run,
)

_NONCE_TTL_SECONDS = 900


class _NonceStore:
    """In-memory replay-nonce set with TTL (strict mode only; the endpoint is on-demand/short-lived)."""

    def __init__(self, ttl_seconds: int = _NONCE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()  # M1: prune+check+add is a TOCTOU race under concurrent requests

    def use(self, nonce: str, *, now: Optional[float] = None) -> bool:
        """Return True if the nonce is fresh (and record it); False if already used within the TTL."""
        now = time.time() if now is None else now
        with self._lock:
            self._seen = {n: t for n, t in self._seen.items() if now - t <= self._ttl}  # prune
            if nonce in self._seen:
                return False
            self._seen[nonce] = now
            return True


@dataclass
class RunServerConfig:
    project_root: Path | str
    token: str
    model: str
    scope_project: str = "stakeholder-panel"
    strict: bool = False
    allowed_origins: Tuple[str, ...] = ()
    # injectable for tests / wiring (real callers leave these None → constructed on demand)
    budget_manager: Any = None
    cost_tracker: Any = None
    panel_factory: Optional[Callable[..., Any]] = None
    pricing: Any = None
    nonces: _NonceStore = field(default_factory=_NonceStore)


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


async def _json_body(request: Request) -> Any:
    """Parse a JSON object body; return the dict, or a 400 JSONResponse the caller must return."""
    try:
        body = await request.json()
    except Exception:
        return _err(400, "invalid JSON body")
    if not isinstance(body, dict):
        return _err(400, "JSON body must be an object")
    return body


def _authorize(request: Request, config: RunServerConfig) -> Optional[JSONResponse]:
    """Return an error response if the request is not authorized, else None."""
    provided: Optional[str] = None
    auth = request.headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        provided = auth[7:]
    if not provided:
        provided = request.headers.get("x-api-key")
    if not provided or not hmac.compare_digest(str(provided), config.token):
        return _err(401, "unauthorized")
    if config.strict:
        origin = request.headers.get("origin")
        if config.allowed_origins and origin not in config.allowed_origins:
            return _err(403, "origin not allowed")
        nonce = request.headers.get("x-nonce")
        if not nonce or not config.nonces.use(nonce):
            return _err(403, "missing or replayed nonce")
    return None


def _load_roster(config: RunServerConfig) -> Any:
    from startd8.stakeholder_panel import load_roster

    path = Path(config.project_root).expanduser() / "docs" / "kickoff" / "inputs" / "stakeholders.yaml"
    if not path.is_file():
        return None
    return load_roster(path)


def _cost_db(config: RunServerConfig) -> Path:
    return Path(config.project_root).expanduser() / ".startd8" / "costs.db"


def _default_manager(config: RunServerConfig) -> Any:
    from startd8.costs.budget import BudgetManager
    from startd8.costs.store import CostStore

    return BudgetManager(CostStore(_cost_db(config)))


def _default_cost_tracker(config: RunServerConfig) -> Any:
    """A real cost tracker so actual per-run spend is recorded (FR-9) — same CostStore as the budget."""
    from startd8.costs.pricing import PricingService
    from startd8.costs.store import CostStore
    from startd8.costs.tracker import CostTracker

    return CostTracker(CostStore(_cost_db(config)), PricingService())


async def _run(request: Request) -> JSONResponse:
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        return _err(400, "invalid JSON body")

    question = str(body.get("question") or "").strip()
    if not question:
        return _err(400, "question is required")
    cap = body.get("cap")
    model = body.get("model") or config.model

    roster = _load_roster(config)
    if roster is None or not getattr(roster, "personas", None):
        return _err(400, "no stakeholder roster — run `startd8 kickoff instantiate` first")

    # Dry-run: honest estimate + a run_key. No spend.
    if body.get("dry_run"):
        return JSONResponse(dry_run(roster, question, cap=cap, model=model, pricing=config.pricing).to_dict())

    run_key = body.get("run_key")
    if not run_key:
        return _err(400, "run_key is required for a confirmed run (obtain it from a dry_run)")

    manager = config.budget_manager or _default_manager(config)
    tracker = config.cost_tracker if config.cost_tracker is not None else _default_cost_tracker(config)
    try:
        result = await run_in_threadpool(
            execute_run,
            roster,
            project_root=config.project_root,
            question=question,
            cap=cap,
            model=model,
            run_key=run_key,
            budget_manager=manager,
            scope_project=config.scope_project,
            cost_tracker=tracker,
            panel_factory=config.panel_factory,
        )
    except BudgetNotConfiguredError as exc:
        return _err(412, str(exc))  # Precondition Failed — fail-closed refusal
    except RunKeyMismatchError as exc:
        return _err(409, str(exc))  # Conflict — run_key doesn't match its params
    except StakeholderRunError as exc:
        return _err(400, str(exc))
    except Exception as exc:  # provider/panel failure — clean message, not a traceback
        return _err(502, f"run failed: {exc}")
    return JSONResponse(result.to_dict())


async def _status(request: Request) -> JSONResponse:
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    session_id = request.path_params["session_id"]
    from startd8.stakeholder_panel.transcript import TranscriptStore

    try:
        answers = TranscriptStore(config.project_root, session_id).load()
    except ValueError:
        return _err(400, "invalid session id")
    except Exception:
        answers = []
    if not answers:
        return _err(404, f"no run '{session_id}'")
    return JSONResponse(
        {"session_id": session_id, "count": len(answers), "answers": [a.to_dict() for a in answers]}
    )


async def _cancel(request: Request) -> JSONResponse:
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    run_key = request.path_params["run_key"]
    ok = cancel_run(run_key)  # signals the in-flight run (FR-12); already-answered personas persist
    return JSONResponse({"run_key": run_key, "cancelled": ok}, status_code=200 if ok else 404)


# --------------------------------------------------------------------------- pipeline drive ($0)
#
# The panel-processing pipeline routes (Increment 3, FR-R1..R6). Each threads THROUGH the CLI code
# paths (`synthesis_bridge`, `ProposalStore`, `vipp`) — never re-implementing pipeline logic — and
# reuses the same bearer-token/posture auth as the run endpoint. Everything here is $0 except an
# opt-in narrative negotiate, which spends through `run_vipp_negotiate`'s OWN `max_cost_usd` ceiling
# (NOT the run preflight — CRP F-8 / FR-R6): the route requires + forwards that ceiling explicitly.
# The write-touching gate (apply) is deliberately absent — it lands last, isolated, in M-apply.


async def _triage(request: Request) -> JSONResponse:
    """FR-R2 — triage a facilitated synthesis into a routing report ($0, read-only)."""
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body

    from startd8.kickoff_view import KickoffViewService
    from startd8.stakeholder_panel.synthesis_bridge import build_triage

    service = KickoffViewService(str(config.project_root))
    sid = str(body.get("session_id") or "").strip() or service.latest_session_id()
    if not sid:
        return _err(404, "no kickoff-panel sessions — run a facilitated panel first")
    try:
        transcript = await run_in_threadpool(service.load, sid)
    except (FileNotFoundError, KeyError):
        return _err(404, f"no such session: {sid}")
    except ValueError:
        return _err(400, "invalid session id")

    report = build_triage(transcript)  # tolerates an absent synthesis (empty candidates) — degrade clean
    synthesis = getattr(transcript, "synthesis", None)
    synthesis_present = bool(getattr(synthesis, "text", "") if synthesis is not None else "")
    return JSONResponse({**report.to_dict(), "synthesis_present": synthesis_present})


async def _disposition(request: Request) -> JSONResponse:
    """FR-R4 — set a staged recommendation's disposition ($0, the human accept/reject gate).

    Pins the exact literals ``"accepted"``/``"rejected"`` (``serialize`` filters ``== "accepted"``; the
    store docstring's "approved" is a trap) and surfaces the no-op-when-unstaged as a 404 rather than a
    false success (``update_disposition`` returns False if the rec was never staged).
    """
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body

    session_id = str(body.get("session_id") or "").strip()
    domain = str(body.get("domain") or "").strip()
    value_path = str(body.get("value_path") or "").strip()
    disposition = str(body.get("disposition") or "").strip()
    if not session_id or not value_path or not disposition:
        return _err(400, "session_id, value_path, and disposition are required")
    if disposition not in ("accepted", "rejected"):
        return _err(400, "disposition must be exactly 'accepted' or 'rejected'")

    from startd8.stakeholder_panel.proposals import ProposalStore

    try:
        store = ProposalStore(config.project_root, session_id)
    except ValueError:
        return _err(400, "invalid session id")
    updated = await run_in_threadpool(store.update_disposition, domain, value_path, disposition)
    if not updated:
        return _err(404, f"no staged recommendation for ({domain!r}, {value_path!r}) — stage it first")
    return JSONResponse(
        {"session_id": session_id, "domain": domain, "value_path": value_path,
         "disposition": disposition, "updated": True}
    )


async def _serialize(request: Request) -> JSONResponse:
    """FR-R5 — serialize ACCEPTED staged recommendations into the VIPP inbox ($0).

    Non-allow-listed paths are **rejected, not dropped** (``serialize_accepted_to_vipp`` reports them).
    """
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body

    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        return _err(400, "session_id is required")

    from startd8.concierge.safe_write import SafeWriteError
    from startd8.stakeholder_panel.proposals import ProposalStore
    from startd8.stakeholder_panel.synthesis_bridge import serialize_accepted_to_vipp

    try:
        recs = await run_in_threadpool(ProposalStore(config.project_root, session_id).load)
    except ValueError:
        return _err(400, "invalid session id")
    if not recs:
        return _err(404, "no staged recommendations — extract → stage first")
    if not any(getattr(r, "disposition", "") == "accepted" for r in recs):
        return _err(409, "no recommendation is marked accepted — disposition one first")

    try:
        result = await run_in_threadpool(
            serialize_accepted_to_vipp, config.project_root, recs, accepted_only=True
        )
    except SafeWriteError as exc:  # confinement / symlink refusal
        return _err(403, f"serialize blocked: {exc}")
    return JSONResponse(
        {"staged": result["staged"], "rejected": result["rejected"], "inbox": result["inbox"]}
    )


async def _negotiate(request: Request) -> JSONResponse:
    """FR-R6 — adjudicate the VIPP inbox into a dispositions report ($0 deterministic; narrative paid).

    The deterministic adjudication is ``$0``. An opt-in ``narrative`` prose pass spends through
    ``run_vipp_negotiate``'s own ``max_cost_usd`` ceiling — NOT the run endpoint's preflight (F-8) — so
    the route **requires** that ceiling to be set and forwards it explicitly.
    """
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body

    from startd8.concierge.safe_write import SafeWriteError
    from startd8.kickoff_experience.vipp_seam import inbox_path
    from startd8.vipp import run_vipp_negotiate

    ip = inbox_path(config.project_root)
    if not ip.exists():
        return _err(409, "no VIPP inbox — serialize accepted recommendations first")

    narrative = bool(body.get("narrative"))
    max_cost_usd = body.get("max_cost_usd")
    agent = None
    if narrative:
        if max_cost_usd is None:
            return _err(400, "narrative negotiate requires an explicit max_cost_usd ceiling (FR-R6)")
        try:
            from startd8.utils.agent_resolution import resolve_agent_spec

            agent = resolve_agent_spec(config.model)
        except Exception as exc:  # provider/config failure — clean message, not a traceback
            return _err(502, f"could not construct narrative agent: {exc}")

    try:
        outcome = await run_in_threadpool(
            run_vipp_negotiate,
            ip,
            project_root=config.project_root,
            narrative=narrative,
            agent=agent,
            max_cost_usd=max_cost_usd,
            write=True,
            force=False,
        )
    except SafeWriteError as exc:  # confinement / symlink refusal
        return _err(403, f"negotiate blocked: {exc}")
    except ValueError as exc:  # future-protocol / malformed / symlink'd inbox
        return _err(400, f"unreadable or invalid inbox: {exc}")
    except Exception as exc:  # provider failure on the narrative path
        return _err(502, f"negotiate failed: {exc}")

    report = outcome.report
    return JSONResponse(
        {"skipped": outcome.skipped, "report_path": str(outcome.report_path),
         "counts": report.counts(), "report": report.to_dict()}
    )


async def _healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_stakeholder_run_app(config: RunServerConfig) -> Starlette:
    """Build the Starlette app. Refuses (ValueError) without a token — a spend endpoint is never anon."""
    if not config.token:
        raise ValueError("a bearer token is required (a non-loopback spend endpoint must not be anonymous)")
    # M3: build the budget manager + cost tracker ONCE (not per request → no repeated SQLite opens /
    # write contention). Injected values (tests, the CLI's ceiling-registered manager) are preserved.
    if config.budget_manager is None:
        config.budget_manager = _default_manager(config)
    if config.cost_tracker is None:
        config.cost_tracker = _default_cost_tracker(config)
    app = Starlette(
        routes=[
            Route("/stakeholders/run", _run, methods=["POST"]),
            Route("/stakeholders/run/{run_key}/cancel", _cancel, methods=["POST"]),
            Route("/stakeholders/run/{session_id}", _status, methods=["GET"]),
            # Increment 3 pipeline drive ($0; narrative negotiate spends its own ceiling) — FR-R1..R6.
            Route("/stakeholders/triage", _triage, methods=["POST"]),
            Route("/stakeholders/disposition", _disposition, methods=["POST"]),
            Route("/stakeholders/serialize", _serialize, methods=["POST"]),
            Route("/stakeholders/negotiate", _negotiate, methods=["POST"]),
            Route("/healthz", _healthz, methods=["GET"]),
        ]
    )
    app.state.config = config
    return app


def serve_stakeholder_run(config: RunServerConfig, *, host: str = "0.0.0.0", port: int = 8710) -> None:  # pragma: no cover
    """Run the endpoint (uvicorn). host defaults to 0.0.0.0 for host.docker.internal reachability."""
    import uvicorn

    uvicorn.run(build_stakeholder_run_app(config), host=host, port=port)
