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
``max_cost_usd`` ceiling), plus the one PAID step ``…/extract`` (dry-run estimate → checksum-gated
confirm, keyed on ``session_id + synthesis-checksum``). The write gate ``…/apply/{preview,ratify}``
(FR-R7) is OFF unless ``enable_apply`` **and** ``strict=True``: a pure preview issues a stateless HMAC
challenge; ratify verifies it, refuses a stale/changed set, and applies only the echoed proposal ids.
It is **token-gated, not human-proof**.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
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

from .facilitate_run import (
    FacilitationCapError,
    cancel_facilitation,
    facilitate_dry_run,
    facilitate_run_key,
    facilitate_status,
    start_facilitation,
)
from .stakeholder_run import (
    BudgetNotConfiguredError,
    IdempotencyStore,
    RunKeyMismatchError,
    StakeholderRunError,
    cancel_run,
    dry_run,
    ensure_blocking_budget,
    execute_run,
    roster_version,
)
from ..logging_config import get_logger

logger = get_logger(__name__)

# Char budget for the extract prompt scaffold (the fixed instructions + allow-list wrapped around the
# synthesis) — folded into the pre-call token estimate so it isn't a systematic under-count.
_EXTRACT_SCAFFOLD_CHARS = 1200

_NONCE_TTL_SECONDS = 900

# M-apply (FR-R7): the ratify challenge is a stateless HMAC over {seq, content-hash, expiry}. The
# signing key is persisted per-project (survives restart) and single-use is enforced via the reused
# IdempotencyStore. Short-lived: a preview must be ratified promptly or re-taken.
_CHALLENGE_TTL_SECONDS = 300
_APPLY_KEY_REL = Path(".startd8") / "stakeholder-run" / "apply-hmac.key"


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
    # M-apply (FR-R7): the write-to-source-of-record gate is OFF unless explicitly enabled, AND it
    # additionally requires strict=True at request time (mandatory Origin allow-list + replay nonce).
    enable_apply: bool = False
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


def _authorize(request: Request, config: RunServerConfig, *, consume_nonce: bool = True) -> Optional[JSONResponse]:
    """Return an error response if the request is not authorized, else None.

    ``consume_nonce=False`` (H-14) checks the nonce is present + valid but does NOT burn it — the caller
    consumes it only after a successful spawn (via :func:`_consume_nonce`), so a spawn failure doesn't
    deny the retry with the same nonce.
    """
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
        if not nonce:
            return _err(403, "missing nonce")
        if consume_nonce and not config.nonces.use(nonce):
            return _err(403, "missing or replayed nonce")
    return None


def _consume_nonce(request: Request, config: RunServerConfig) -> None:
    """Burn the request's nonce after a successful spawn (H-14). Best-effort; the single-flight gate is
    the real double-spend guard, so a lost race here can't double-charge."""
    if config.strict:
        nonce = request.headers.get("x-nonce")
        if nonce:
            config.nonces.use(nonce)


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


# --------------------------------------------------------------------------- F1: facilitation over HTTP


def _build_facilitation_config(config: "RunServerConfig", *, posture: str, tier: str, cap: Any, budget_usd: float, body: dict) -> Any:
    from startd8.stakeholder_panel.context_resolver import resolve_context
    from startd8.stakeholder_panel.facilitation import FacilitationConfig

    root = Path(config.project_root).expanduser()
    ctx = resolve_context(root, desc=body.get("desc"), objective=body.get("objective"),
                          strategy=body.get("strategy"))
    return FacilitationConfig(
        project=root, objective=ctx.objective, strategy=ctx.strategy, desc=ctx.desc,
        posture=posture, tier=tier, cap=int(cap) if cap else 0, budget_usd=budget_usd,
    )


async def _facilitate(request: Request) -> JSONResponse:
    """FR-1/FR-2 — kick off (or preview) a multi-round facilitation. Fire-and-poll; async."""
    from startd8.stakeholder_panel.facilitation import POSTURES, TIERS

    config: RunServerConfig = request.app.state.config
    is_dry = False
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body
    is_dry = bool(body.get("dry_run"))
    # H-14: a confirm authorizes WITHOUT burning the nonce (consumed only on a successful spawn).
    denied = _authorize(request, config, consume_nonce=is_dry)
    if denied is not None:
        return denied

    posture = str(body.get("posture") or "scrutiny")
    tier = str(body.get("tier") or "premium")
    if posture not in POSTURES:
        return _err(400, f"posture must be one of {sorted(POSTURES)}")
    if tier not in TIERS:
        return _err(400, f"tier must be one of {sorted(TIERS)}")
    roster = _load_roster(config)
    if roster is None or not getattr(roster, "personas", None):
        return _err(400, "no stakeholder roster — run `startd8 kickoff instantiate` first")
    cfg = _build_facilitation_config(config, posture=posture, tier=tier, cap=body.get("cap"),
                                     budget_usd=float(body.get("budget_usd") or 0.0), body=body)

    # H-13: the dry-run also runs the fail-closed budget check (a green preview must not precede a 412).
    manager = config.budget_manager or _default_manager(config)
    try:
        ensure_blocking_budget(manager, scope_project=config.scope_project)
    except BudgetNotConfiguredError as exc:
        return _err(412, str(exc))

    if is_dry:
        return JSONResponse(facilitate_dry_run(cfg, roster, pricing=config.pricing).to_dict())

    run_key = body.get("run_key")
    if not run_key:
        return _err(400, "run_key is required for a confirmed facilitation (obtain it from a dry_run)")
    # H-10: the confirm's params must match the previewed run_key (a cheap preview can't run premium).
    expected = facilitate_run_key(posture=cfg.posture, tier=cfg.tier, cap=(cfg.cap or None),
                                  budget_usd=cfg.budget_usd, rv=roster_version(roster))
    if run_key != expected:
        return _err(409, "run_key does not match posture/tier/params — re-preview (dry_run)")

    tracker = config.cost_tracker if config.cost_tracker is not None else _default_cost_tracker(config)
    try:
        result = await run_in_threadpool(start_facilitation, cfg, roster, cost_tracker=tracker)
    except FacilitationCapError as exc:
        return _err(429, str(exc))
    except RunKeyMismatchError as exc:
        return _err(409, str(exc))
    except Exception as exc:  # noqa: BLE001
        return _err(502, f"facilitate failed: {exc}")
    _consume_nonce(request, config)  # H-14 — burn the nonce only now (spawn succeeded / deduped)
    return JSONResponse(result)


async def _facilitate_status(request: Request) -> JSONResponse:
    """FR-3 — poll the facilitation transcript (reads the kickoff-panel store, H-15)."""
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    sid = request.path_params["session_id"]
    return JSONResponse(await run_in_threadpool(facilitate_status, config.project_root, sid))


async def _facilitate_cancel(request: Request) -> JSONResponse:
    """FR-6/H-9 — cancel by the session_id the poller holds."""
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    sid = request.path_params["session_id"]
    ok = cancel_facilitation(config.project_root, sid)
    return JSONResponse({"session_id": sid, "cancelled": ok}, status_code=200 if ok else 404)


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
    from startd8.stakeholder_panel.synthesis_bridge import build_triage, render_backlog_section

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
    synthesis_text = getattr(synthesis, "text", "") if synthesis is not None else ""
    synthesis_present = bool(synthesis_text)
    # M1a (FR-4): reuse the tested renderer server-side so the Triage panel previews the backlog without
    # re-implementing it in TS (Mottainai). `""` when there are no candidates. Additive field (M1a test
    # asserts the response stays a superset of the prior keys).
    project_name = Path(config.project_root).expanduser().name
    backlog_markdown = render_backlog_section(report, project=project_name)
    # FR-12 staleness guard: return the checksum of the synthesis these candidates were triaged from, so
    # the panel can detect a re-facilitation between triage and extract (the SAME `_synthesis_checksum` the
    # paid extract confirm echoes) and surface "synthesis changed — re-triage" rather than acting on stale
    # candidates. Empty when there's no synthesis.
    synthesis_checksum = _synthesis_checksum(synthesis_text) if synthesis_text else ""
    return JSONResponse(
        {**report.to_dict(), "synthesis_present": synthesis_present, "backlog_markdown": backlog_markdown,
         "synthesis_checksum": synthesis_checksum}
    )


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
    # M1d (FR-10b): `serialize_buffer` is no-clobber — an existing UNDRAINED inbox is skipped, not
    # overwritten, and nothing is written. Returning 200 here (as before) told the operator serialize
    # succeeded while the inbox held stale content; Apply mode would then ratify the wrong set. Surface
    # the skip as a 409 so the operator drains (ratifies) it in Apply mode first.
    write = result.get("write")
    if write is not None and getattr(write, "skipped", None):
        return _err(409, "undrained inbox — consume it in Apply mode (preview → ratify) before re-serializing")
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


# --------------------------------------------------------------------------- pipeline drive (PAID)
#
# FR-R3 extract→stage — the ONE paid step in the panel-processing pipeline. `extract_field_mappings`
# (LLM) maps synthesis prose → allow-listed field edits; `stage_recommendations` ($0) persists them as
# unratified drafts. dry-run → confirm mirrors the run endpoint's UX, but the preflight is keyed on
# `(session_id + synthesis-checksum)` — NOT `run_key` (which binds question/cap/roster) — per CRP F-8.


def _synthesis_checksum(text: str) -> str:
    """Stable content hash of the synthesis being extracted — the FR-R3 idempotency basis."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _derive_extract_key(session_id: str, checksum: str) -> str:
    """Opaque key binding {session_id, synthesis-checksum} — minted at dry-run, echoed at confirm."""
    blob = f"extract:{session_id}:{checksum}"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _tracked_extract_mapper(model: str, cost_tracker: Any, pricing: Any, spent: dict) -> Callable[[str], str]:
    """A paid mapper that records ACTUAL token spend (FR-9 parity) into *spent*.

    The default synthesis-bridge mapper discards token usage; this one captures ``result.token_usage``,
    prices it via the same pricing stack the estimate used, and records it to the ``CostTracker`` so
    extract spend is attributed exactly like a run-endpoint call. Cost recording is best-effort — it
    must never break the extraction result itself.
    """

    def mapper(prompt: str) -> str:
        import asyncio

        from startd8.utils.agent_resolution import resolve_agent_spec

        agent = resolve_agent_spec(model)
        result = asyncio.run(agent.agenerate(prompt))
        usage = getattr(result, "token_usage", None)
        in_tok = int(getattr(usage, "input", 0) or 0)
        out_tok = int(getattr(usage, "output", 0) or 0)
        spent["input_tokens"] = in_tok
        spent["output_tokens"] = out_tok
        try:
            spent["cost"] = float(pricing.calculate_total_cost(model, in_tok, out_tok))
        except Exception:  # pragma: no cover - pricing optional / unknown model
            spent["cost"] = 0.0
        if cost_tracker is not None and usage is not None:
            try:
                cost_tracker.record_cost(
                    agent_name="stakeholder-extract", model=model,
                    input_tokens=in_tok, output_tokens=out_tok, tags=["stakeholder-extract"],
                )
            except Exception:  # pragma: no cover - recording must not break extraction
                pass
        return getattr(result, "text", "") or ""

    return mapper


async def _extract(request: Request) -> JSONResponse:
    """FR-R3 — extract synthesis → staged recommendations (the ONE paid pipeline step).

    ``dry_run`` returns a token-based estimate + a ``synthesis_checksum`` (``$0``); a confirm echoes the
    checksum, is deduped on ``(session_id + checksum)``, fail-closes on the blocking budget, and gates on
    ``max_cost_usd`` before spending. Actual spend is recorded (FR-9); staged output is UNRATIFIED.
    """
    config: RunServerConfig = request.app.state.config
    if (denied := _authorize(request, config)) is not None:
        return denied
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body

    from startd8.kickoff_experience.manifest import default_config
    from startd8.kickoff_view import KickoffViewService
    from startd8.stakeholder_panel.synthesis_bridge import extract_field_mappings, stage_recommendations

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

    synthesis = getattr(transcript, "synthesis", None)
    synthesis_text = getattr(synthesis, "text", "") if synthesis is not None else ""
    if not (synthesis_text or "").strip():
        return _err(422, "session has no facilitated synthesis to extract from (ask-all runs have none)")

    checksum = _synthesis_checksum(synthesis_text)
    extract_key = _derive_extract_key(sid, checksum)
    allowed = default_config().allowed_value_paths()

    # Token-based estimate (never a spend): synthesis + scaffold in, a bounded mapping payload out.
    from startd8.costs.pricing import PricingService

    pricing = config.pricing or PricingService()
    prompt_chars = len(synthesis_text) + _EXTRACT_SCAFFOLD_CHARS + sum(len(p) for p in allowed)
    estimated = float(pricing.estimate_cost(config.model, prompt_chars, expected_output_chars=len(allowed) * 120))

    if body.get("dry_run"):
        return JSONResponse(
            {"session_id": sid, "synthesis_checksum": checksum, "extract_key": extract_key,
             "estimated_cost": round(estimated, 6), "model": config.model, "n_allowed": len(allowed),
             "note": "estimate — real cost is only known after extraction"}
        )

    # Confirm: the echoed checksum must match the CURRENT synthesis (a concurrent edit → re-preview).
    if str(body.get("confirm_checksum") or "") != checksum:
        return _err(409, "synthesis changed since preview — re-run dry_run for a fresh checksum")

    store = IdempotencyStore(config.project_root)
    try:
        prior = store.lookup(extract_key, checksum)
    except RunKeyMismatchError as exc:
        return _err(409, str(exc))
    if prior and prior.get("status") == "completed":
        from startd8.stakeholder_panel.proposals import ProposalStore

        recs = await run_in_threadpool(ProposalStore(config.project_root, sid).load)
        return JSONResponse(
            {"session_id": sid, "status": "deduped",
             # M1b (FR-9a): `domain` is required to build a /disposition (domain, value_path) call.
             "staged": [{"domain": r.domain, "value_path": r.value_path, "value": r.recommended_value}
                        for r in recs],
             "synthesis_checksum": checksum,
             "note": "idempotent replay — prior extraction returned, no re-charge"}
        )

    manager = config.budget_manager or _default_manager(config)
    try:
        ensure_blocking_budget(manager, scope_project=config.scope_project)  # fail-CLOSED
    except BudgetNotConfiguredError as exc:
        return _err(412, str(exc))

    # Pre-call ceiling: refuse to spend if the honest estimate already blows the cap (prevents the spend).
    max_cost = body.get("max_cost_usd")
    if max_cost is not None and estimated > float(max_cost):
        return _err(412, f"estimated ${estimated:.4f} exceeds max_cost_usd ${float(max_cost):.4f} — refusing")

    # M1c (FR-8a): atomically CLAIM the spend. `reserve()` writes the marker AND detects a concurrent
    # confirm in ONE locked region — `record_start` was not atomic vs the earlier `lookup`, so two
    # confirms sharing an `extract_key` could both pass and both spend. Placed AFTER the budget/ceiling
    # checks, so a 412 never leaves a reservation (mirrors the original record_start ordering).
    try:
        claim = store.reserve(extract_key, checksum)
    except RunKeyMismatchError as exc:
        return _err(409, str(exc))
    if claim is not None:  # a concurrent confirm won the race between our lookup and here
        if claim.get("status") == "completed":
            from startd8.stakeholder_panel.proposals import ProposalStore

            recs = await run_in_threadpool(ProposalStore(config.project_root, sid).load)
            return JSONResponse(
                {"session_id": sid, "status": "deduped",
                 "staged": [{"domain": r.domain, "value_path": r.value_path, "value": r.recommended_value}
                            for r in recs],
                 "synthesis_checksum": checksum,
                 "note": "idempotent replay — a concurrent extraction returned, no re-charge"}
            )
        return _err(409, "extraction already in progress for this synthesis — retry shortly")

    spent: dict = {"cost": 0.0, "input_tokens": 0, "output_tokens": 0}
    mapper = _tracked_extract_mapper(config.model, config.cost_tracker, pricing, spent)
    try:
        mappings = await run_in_threadpool(extract_field_mappings, synthesis_text, allowed, mapper=mapper)
    except Exception as exc:  # provider/mapper failure — release the claim so a retry can re-run
        store.release(extract_key)
        return _err(502, f"extraction failed: {exc}")

    recs = await run_in_threadpool(stage_recommendations, config.project_root, sid, mappings)
    store.mark_complete(extract_key, sid)
    # Mottainai: the call already charged, so we KEEP the staged output even if actuals topped the cap —
    # we surface the overage (ceiling_exceeded) rather than discard paid-for work.
    ceiling_exceeded = max_cost is not None and float(spent["cost"]) > float(max_cost)
    return JSONResponse(
        {"session_id": sid, "status": "staged",
         # M1b (FR-9a): `domain` per staged row so the panel can build the /disposition call.
         "staged": [{"domain": r.domain, "value_path": r.value_path, "value": r.recommended_value}
                    for r in recs],
         "synthesis_checksum": checksum, "actual_cost": round(float(spent["cost"]), 6),
         "input_tokens": spent["input_tokens"], "output_tokens": spent["output_tokens"],
         "ceiling_exceeded": ceiling_exceeded,
         "note": "SYNTHETIC & UNRATIFIED — review, mark accepted, then serialize into the VIPP inbox"}
    )


# --------------------------------------------------------------------------- pipeline apply (WRITE)
#
# FR-R7 — THE gate. Writes the project source of record. Two requests: a PURE preview (reconstructs the
# would-apply set with zero side effects, never calls apply_dispositions) that returns a stateless HMAC
# challenge, and a ratify that verifies the challenge, refuses on a stale seq / changed set, then applies
# ONLY the echoed proposal_ids. **Token-gated, not human-proof** (CRP F-2): a token holder can drive
# preview→ratify — the guarantees are that apply is a deliberate two-request act bound to exactly the
# previewed set, and that strict mode (Origin allow-list + replay nonce) is MANDATORY here.


def _apply_hmac_key(config: RunServerConfig) -> bytes:
    """Per-project signing key for the ratify challenge, persisted 0600 so it survives restart (F-4)."""
    path = Path(config.project_root).expanduser() / _APPLY_KEY_REL
    if path.is_file():
        return path.read_bytes()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # atomic exclusive create
    except FileExistsError:  # a concurrent first-request won the race — read theirs
        return path.read_bytes()
    with os.fdopen(fd, "wb") as fh:
        fh.write(key)
    return key


def _issue_challenge(key: bytes, seq: int, content_hash: str, *, ttl: int = _CHALLENGE_TTL_SECONDS) -> str:
    """Sign {seq, content-hash, expiry} into a stateless single-use token: ``<b64(payload)>.<hmac>``."""
    payload = json.dumps(
        {"seq": int(seq), "ch": content_hash, "exp": time.time() + ttl}, sort_keys=True
    )
    b = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = hmac.new(key, b.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b}.{sig}"


def _verify_challenge(key: bytes, token: str) -> Optional[dict]:
    """Return the decoded payload iff the HMAC verifies (constant-time); else None."""
    try:
        b, sig = token.split(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = hmac.new(key, b.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(b.encode("ascii")).decode("utf-8"))
    except Exception:
        return None


def _apply_guard(request: Request, config: RunServerConfig) -> Optional[JSONResponse]:
    """Shared gate for both apply routes: auth, explicit enable, and MANDATORY strict mode (FR-R7 c)."""
    if (denied := _authorize(request, config)) is not None:
        return denied
    if not config.enable_apply:
        return _err(404, "apply route is not enabled on this endpoint")
    if not config.strict:
        return _err(403, "apply requires strict mode (Origin allow-list + replay nonce) — refusing")
    return None


def _confined_apply_root(config: RunServerConfig) -> Any:
    """Resolve the confined project root (FR-C5) — apply_dispositions does NOT confine itself. Returns
    the resolved Path, or a JSONResponse error the caller must return."""
    from startd8.concierge.safe_write import SafeWriteError, resolve_confined_root

    try:
        return resolve_confined_root(config.project_root)
    except SafeWriteError as exc:
        return _err(403, f"confinement refused: {exc}")


def _apply_consensus(project_root: Any, source_session_id: str) -> dict:
    """#8 — the source facilitation's consensus for the apply preview (FLAG). ALWAYS returns a consensus
    dict ({label, score, n, basis}); degrades to n/a on any problem and warns ONLY on a genuine exception
    so a silently-broken signal stays observable (FR-1/FR-2a/FR-6). Lazy imports keep `startd8.vipp` free
    of any facilitation dependency (the consensus lives on the route side, not in vipp)."""
    from startd8.kickoff_view import KickoffViewService
    from startd8.kickoff_view.store import _safe_session_component
    from startd8.stakeholder_panel.consensus import ConsensusResult, compute_consensus
    from startd8.stakeholder_panel.facilitation import CHALLENGER_IDS

    na = ConsensusResult(label="n/a", score=None, n=0, basis="lexical-r1").to_dict()
    sid = (source_session_id or "").strip()
    if not sid:
        return na  # pre-#8 inbox / mixed-session (empty by FR-2b) → benign n/a
    try:
        _safe_session_component(sid)  # FR-2a — path-traversal guard BEFORE any filesystem load
    except ValueError:
        logger.warning("apply preview: refusing unsafe source_session_id %r for consensus", sid)
        return na
    try:
        transcript = KickoffViewService(str(project_root)).load(sid)
    except (FileNotFoundError, KeyError):
        return na  # benign — missing/absent transcript
    except Exception as exc:  # noqa: BLE001 — never break the preview; but surface a real failure
        logger.warning("apply preview: transcript load failed for %r: %s", sid, exc)
        return na
    try:
        return compute_consensus(
            getattr(transcript, "rounds", []) or [], exclude_role_ids=frozenset(CHALLENGER_IDS)
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.warning("apply preview: consensus compute failed for %r: %s", sid, exc)
        return na


async def _apply_preview(request: Request) -> JSONResponse:
    """FR-R7 preview — PURE reconstruct of the would-apply set + a stateless HMAC challenge. No writes."""
    config: RunServerConfig = request.app.state.config
    if (denied := _apply_guard(request, config)) is not None:
        return denied
    root = _confined_apply_root(config)
    if isinstance(root, JSONResponse):
        return root

    from startd8.vipp import preview_dispositions

    try:
        preview = await run_in_threadpool(preview_dispositions, root)
    except Exception as exc:  # malformed inbox/dispositions — clean message
        return _err(502, f"preview failed: {exc}")
    if preview.refused_reason:
        return JSONResponse(
            {"would_apply": [], "stale": preview.stale, "refused_reason": preview.refused_reason},
            status_code=409,
        )

    challenge = _issue_challenge(_apply_hmac_key(config), preview.envelope_seq, preview.content_hash)
    # #8 — best-effort consensus of the SOURCE facilitation, in a SEPARATE inner path AFTER the preview
    # succeeded (FR-6): a consensus failure degrades to n/a and never turns into a 502.
    consensus = await run_in_threadpool(_apply_consensus, root, getattr(preview, "source_session_id", ""))
    return JSONResponse(
        {
            "would_apply": preview.would_apply,
            "envelope_seq": preview.envelope_seq,
            "content_hash": preview.content_hash,
            "challenge": challenge,
            "expires_in_seconds": _CHALLENGE_TTL_SECONDS,
            "posture": "token-gated, not human-proof — any holder of the endpoint token can ratify",
            "consensus": consensus,  # FR-1 always present; FR-9 source_session_id is NOT echoed
        }
    )


async def _apply_ratify(request: Request) -> JSONResponse:
    """FR-R7 ratify — verify the challenge, refuse a stale/changed set, then apply ONLY the echoed ids."""
    config: RunServerConfig = request.app.state.config
    if (denied := _apply_guard(request, config)) is not None:
        return denied
    body = await _json_body(request)
    if isinstance(body, JSONResponse):
        return body

    proposal_ids = body.get("proposal_ids")
    challenge = body.get("challenge")
    if not isinstance(proposal_ids, list) or not proposal_ids:
        return _err(400, "proposal_ids (a non-empty list) is required")
    if not isinstance(challenge, str) or not challenge:
        return _err(400, "challenge is required")

    payload = _verify_challenge(_apply_hmac_key(config), challenge)
    if payload is None:
        return _err(403, "invalid or forged challenge")
    if float(payload.get("exp", 0)) < time.time():
        return _err(403, "challenge expired — re-preview")

    root = _confined_apply_root(config)
    if isinstance(root, JSONResponse):
        return root

    from startd8.vipp import apply_dispositions, preview_dispositions

    # Single-use FIRST (persisted, survives restart — F-4): the challenge ratifies exactly once. Consume
    # it before applying so a replay can't ride a race, and so a burned challenge always forces a fresh
    # preview (the correct recovery even after a stale/failed apply).
    sig = challenge.split(".", 1)[-1]
    store = IdempotencyStore(root)
    try:
        prior = store.lookup(sig, str(payload.get("ch")))
    except RunKeyMismatchError:
        return _err(403, "challenge signature/content mismatch")
    if prior is not None:
        return _err(409, "challenge already used — re-preview")
    store.record_start(sig, str(payload.get("ch")))  # consume now

    # Re-preview against the LIVE inbox: the challenge is bound to a specific {seq, content-hash}; a
    # concurrent negotiate/serialize re-seqs the inbox → stale → refuse (F-3). Both must still match.
    live = await run_in_threadpool(preview_dispositions, root)
    if live.refused_reason:
        return _err(409, f"cannot apply: {live.refused_reason}")
    if live.envelope_seq != int(payload.get("seq", -1)):
        return _err(409, "inbox changed since preview (stale envelope_seq) — re-preview")
    if live.content_hash != payload.get("ch"):
        return _err(409, "the would-apply set changed since preview — re-preview")

    ids = {str(p) for p in proposal_ids}

    def _confirm(action: Any, disp: Any) -> bool:  # apply ONLY the human-echoed, still-current ids
        return disp.proposal_id in ids

    from startd8.concierge.safe_write import SafeWriteError

    try:
        # `force` is NEVER exposed (NR-8) — apply_dispositions defaults force=False.
        res = await run_in_threadpool(apply_dispositions, root, confirm=_confirm)
    except SafeWriteError as exc:  # confinement / symlink refusal on the write path
        return _err(403, f"apply blocked: {exc}")
    except Exception as exc:
        return _err(502, f"apply failed: {exc}")
    store.mark_complete(sig, "apply")  # consume the challenge

    return JSONResponse(
        {
            "wrote": res.wrote,
            "actionable": res.actionable,
            "outcomes": res.outcomes,
            "inbox_shredded": res.inbox_shredded,
            "stale": res.stale,
            "refused_reason": res.refused_reason,
        }
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
            # F1 — facilitation over HTTP (fire-and-poll). Distinct `/facilitate/` prefix (no collision
            # with `/run/{session_id}`). Static `/facilitate` registered before the `{session_id}` param.
            Route("/stakeholders/facilitate", _facilitate, methods=["POST"]),
            Route("/stakeholders/facilitate/{session_id}/cancel", _facilitate_cancel, methods=["POST"]),
            Route("/stakeholders/facilitate/{session_id}", _facilitate_status, methods=["GET"]),
            # Increment 3 pipeline drive ($0; narrative negotiate spends its own ceiling) — FR-R1..R6.
            Route("/stakeholders/triage", _triage, methods=["POST"]),
            Route("/stakeholders/disposition", _disposition, methods=["POST"]),
            Route("/stakeholders/serialize", _serialize, methods=["POST"]),
            Route("/stakeholders/negotiate", _negotiate, methods=["POST"]),
            # FR-R3 extract→stage — the one PAID pipeline step (dry-run estimate → checksum-gated confirm).
            Route("/stakeholders/extract", _extract, methods=["POST"]),
            # FR-R7 apply — THE write gate (off unless enable_apply; strict mode mandatory at request time).
            Route("/stakeholders/apply/preview", _apply_preview, methods=["POST"]),
            Route("/stakeholders/apply/ratify", _apply_ratify, methods=["POST"]),
            Route("/healthz", _healthz, methods=["GET"]),
        ]
    )
    app.state.config = config
    return app


def serve_stakeholder_run(config: RunServerConfig, *, host: str = "0.0.0.0", port: int = 8710) -> None:  # pragma: no cover
    """Run the endpoint (uvicorn). host defaults to 0.0.0.0 for host.docker.internal reachability."""
    import uvicorn

    uvicorn.run(build_stakeholder_run_app(config), host=host, port=port)
