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
``GET /stakeholders/run/{session_id}``, ``GET /healthz`` (unauthenticated liveness).
"""

from __future__ import annotations

import hmac
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

    def use(self, nonce: str, *, now: Optional[float] = None) -> bool:
        """Return True if the nonce is fresh (and record it); False if already used within the TTL."""
        now = time.time() if now is None else now
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


async def _healthz(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_stakeholder_run_app(config: RunServerConfig) -> Starlette:
    """Build the Starlette app. Refuses (ValueError) without a token — a spend endpoint is never anon."""
    if not config.token:
        raise ValueError("a bearer token is required (a non-loopback spend endpoint must not be anonymous)")
    app = Starlette(
        routes=[
            Route("/stakeholders/run", _run, methods=["POST"]),
            Route("/stakeholders/run/{run_key}/cancel", _cancel, methods=["POST"]),
            Route("/stakeholders/run/{session_id}", _status, methods=["GET"]),
            Route("/healthz", _healthz, methods=["GET"]),
        ]
    )
    app.state.config = config
    return app


def serve_stakeholder_run(config: RunServerConfig, *, host: str = "0.0.0.0", port: int = 8710) -> None:  # pragma: no cover
    """Run the endpoint (uvicorn). host defaults to 0.0.0.0 for host.docker.internal reachability."""
    import uvicorn

    uvicorn.run(build_stakeholder_run_app(config), host=host, port=port)
