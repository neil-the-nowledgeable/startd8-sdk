"""Phase 2 M0 (core) — orchestrate a stakeholder-panel run behind the real guardrails.

Framework-agnostic core that the HTTP endpoint wraps. It BUILDS the guardrails the CLI path does NOT
wire (CRP F-1/F-2b/F-3/F-4): a fail-closed budget gate + cost tracker + an honest cost estimate + a
``run_key`` idempotency/crash marker. Never runs the LLM in Grafana — this is invoked server-side.

Design (docs/design/kickoff-portal/WORKBOOK_STAKEHOLDER_RUN_*.md, v0.3):
  * **Honest estimate (FR-3):** ``min(cap, len(roster)) × per_question_estimate`` from real pricing —
    NOT ``projected_calls`` (facilitator basis, ×3-4, a call count). Labeled an estimate.
  * **Fail-CLOSED (FR-4):** refuse to run unless a *blocking* budget scoped to the panel is configured
    (``BudgetManager.check_budget`` returns ``[]`` = fail-open otherwise).
  * **run_key integrity (FR-11):** binds ``{question, cap, roster_version}``; the confirm must echo it;
    a matching completed run is deduped (no double charge).
  * **Crash marker (FR-13):** a spend marker is persisted BEFORE the provider call, so a re-submit
    after a crash is recognized and not re-charged.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from startd8.exceptions import Startd8Error

# Conservative per-persona-question token assumption for the pre-spend estimate (real cost is only
# known post-call). Deliberately generous so the estimate does not under-promise.
_EST_INPUT_TOKENS = 2500
_EST_OUTPUT_TOKENS = 600
_FALLBACK_PER_QUESTION_USD = 0.02  # when pricing has no entry for the model
_IDEMPOTENCY_TTL_SECONDS = 3600
_RUN_STATE_REL = Path(".startd8") / "stakeholder-run"


class StakeholderRunError(Startd8Error):
    """Base for run-orchestration errors."""


class BudgetNotConfiguredError(StakeholderRunError):
    """No *blocking* budget is configured — the fail-closed gate refuses to run (CRP F-2b)."""


class RunKeyMismatchError(StakeholderRunError):
    """The confirm's run_key does not match the {question, cap, roster_version} it claims (CRP F-11)."""


# --------------------------------------------------------------------------- estimate / keys


def estimate_cost_per_question(model: str, pricing: Any = None) -> float:
    """Honest per-question dollar *estimate* from real pricing (FR-3). Never the facilitator basis."""
    try:
        from startd8.costs.pricing import PricingService

        svc = pricing or PricingService()
        p = svc.get_pricing(model)
    except Exception:  # pragma: no cover - pricing stack optional
        p = None
    if p is None:
        return _FALLBACK_PER_QUESTION_USD
    return (
        _EST_INPUT_TOKENS * p.input_cost_per_million
        + _EST_OUTPUT_TOKENS * p.output_cost_per_million
    ) / 1_000_000.0


def roster_version(roster: Any) -> str:
    """A stable fingerprint of the roster's personas (binds a run to the roster it previewed)."""
    try:
        personas = roster.to_dict().get("personas", [])
    except Exception:
        personas = [
            {"role_id": getattr(p, "role_id", ""), "display_name": getattr(p, "display_name", "")}
            for p in getattr(roster, "personas", []) or []
        ]
    blob = json.dumps(personas, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def derive_run_key(question: str, cap: Optional[int], rv: str) -> str:
    """Opaque key binding {question, cap, roster_version} — minted at dry-run, echoed at confirm."""
    blob = json.dumps({"q": question, "cap": cap, "rv": rv}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class DryRun:
    """The pre-spend preview (FR-3) — no LLM call happens to produce this."""

    run_key: str
    roster_version: str
    n_personas: int
    per_question_estimate: float
    estimated_cost: float
    model: str
    note: str = "estimate — real cost is only known after the run"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_key": self.run_key,
            "roster_version": self.roster_version,
            "n_personas": self.n_personas,
            "per_question_estimate": round(self.per_question_estimate, 6),
            "estimated_cost": round(self.estimated_cost, 6),
            "model": self.model,
            "note": self.note,
        }


def dry_run(
    roster: Any, question: str, *, cap: Optional[int] = None, model: str, pricing: Any = None
) -> DryRun:
    """Preview a run with an honest cost estimate + a run_key. No spend (FR-3)."""
    n_total = len(getattr(roster, "personas", []) or [])
    n = n_total if cap is None else max(0, min(int(cap), n_total))
    per_q = estimate_cost_per_question(model, pricing)
    rv = roster_version(roster)
    return DryRun(
        run_key=derive_run_key(question, cap, rv),
        roster_version=rv,
        n_personas=n,
        per_question_estimate=per_q,
        estimated_cost=n * per_q,
        model=model,
    )


# --------------------------------------------------------------------------- idempotency / crash marker


class IdempotencyStore:
    """Persisted run-key ledger (FR-11/FR-13). A spend marker is written BEFORE the provider call so a
    crash-then-resubmit is recognized and not re-charged. Records: run_key -> {params_hash, started_at,
    session_id, status}."""

    def __init__(self, project_root: Path | str, *, ttl_seconds: int = _IDEMPOTENCY_TTL_SECONDS) -> None:
        self.dir = Path(project_root).expanduser() / _RUN_STATE_REL
        self.path = self.dir / "idempotency.json"
        self.ttl = ttl_seconds

    def _load(self) -> Dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, data: Dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover
            pass
        fd, tmp = tempfile.mkstemp(dir=str(self.dir), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(data, indent=2, ensure_ascii=False))
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:  # pragma: no cover
                pass
            raise

    def lookup(self, run_key: str, params_hash: str, *, now: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Return the record for *run_key* if present, unexpired, and params-consistent.

        Raises ``RunKeyMismatchError`` if the key exists but for *different* params (a replay with a
        forged/stale key). Returns None if absent or expired.
        """
        now = time.time() if now is None else now
        rec = self._load().get(run_key)
        if rec is None:
            return None
        if now - float(rec.get("started_at", 0)) > self.ttl:
            return None
        if rec.get("params_hash") != params_hash:
            raise RunKeyMismatchError(
                f"run_key {run_key[:8]}… replayed with different params"
            )
        return rec

    def record_start(self, run_key: str, params_hash: str, *, now: Optional[float] = None) -> None:
        """Write the spend marker BEFORE the provider call (FR-13 crash-safety)."""
        now = time.time() if now is None else now
        data = self._load()
        data[run_key] = {"params_hash": params_hash, "started_at": now, "status": "started",
                         "session_id": None}
        self._save(data)

    def mark_complete(self, run_key: str, session_id: str, *, now: Optional[float] = None) -> None:
        data = self._load()
        rec = data.get(run_key) or {"params_hash": None, "started_at": time.time() if now is None else now}
        rec.update(status="completed", session_id=session_id)
        data[run_key] = rec
        self._save(data)


# --------------------------------------------------------------------------- fail-closed budget gate


def ensure_blocking_budget(manager: Any, *, scope_project: str = "stakeholder-panel") -> None:
    """Refuse to proceed unless a *blocking* budget applies to *scope_project* (CRP F-2b, fail-CLOSED).

    ``BudgetManager.check_budget`` silently returns ``[]`` when no blocking budget matches, so without
    this guard the preflight is fail-OPEN. A budget with ``block_on_exceed`` and a matching (or global)
    project scope must exist.
    """
    try:
        budgets = manager.list_budgets(active_only=True)
    except Exception as exc:  # pragma: no cover - defensive
        raise BudgetNotConfiguredError(f"cannot read budgets: {exc}") from exc
    for b in budgets:
        if getattr(b, "block_on_exceed", False) and getattr(b, "scope_project", None) in (None, scope_project):
            return
    raise BudgetNotConfiguredError(
        f"no blocking budget configured for project '{scope_project}' — refusing to run "
        f"(a spend endpoint must fail closed). Create one with block_on_exceed=True."
    )


@dataclass
class RunResult:
    session_id: str
    answers: List[Dict[str, Any]]
    status: str  # "completed" | "deduped" | "partial"
    run_key: str
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "status": self.status,
            "run_key": self.run_key,
            "answers": self.answers,
            "note": self.note,
        }


# A panel factory lets tests inject a fake panel (no LLM spend). Real callers omit it.
PanelFactory = Callable[..., Any]


def execute_run(
    roster: Any,
    *,
    project_root: Path | str,
    question: str,
    cap: Optional[int],
    model: str,
    run_key: str,
    budget_manager: Any,
    scope_project: str = "stakeholder-panel",
    cost_tracker: Any = None,
    panel_factory: Optional[PanelFactory] = None,
    now: Optional[float] = None,
) -> RunResult:
    """Execute a confirmed run behind all guardrails (FR-2/4/6/11/13).

    ``budget_manager`` is REQUIRED (the endpoint constructs it) — this function never runs open. The
    LLM call happens via ``StakeholderPanel.ask_all``; ``panel_factory`` is injectable for tests.
    """
    rv = roster_version(roster)
    expected = derive_run_key(question, cap, rv)
    if run_key != expected:
        raise RunKeyMismatchError("confirm run_key does not match {question, cap, roster_version}")

    store = IdempotencyStore(project_root)
    prior = store.lookup(run_key, expected, now=now)  # raises on params-mismatch replay
    if prior and prior.get("status") == "completed" and prior.get("session_id"):
        return RunResult(prior["session_id"], [], "deduped", run_key,
                         note="idempotent replay — prior run returned, no re-charge")

    # Fail-CLOSED: a blocking budget must exist, and the preflight must gate spend.
    ensure_blocking_budget(budget_manager, scope_project=scope_project)
    from startd8.stakeholder_panel.budget import budget_preflight

    per_q = estimate_cost_per_question(model)
    preflight = budget_preflight(budget_manager, model=model, cost_per_question=per_q, project=scope_project)

    # Crash marker BEFORE any spend (FR-13).
    store.record_start(run_key, expected, now=now)

    if panel_factory is not None:
        panel = panel_factory(
            roster, project_root=project_root, model_spec=model,
            cost_tracker=cost_tracker, cost_project=scope_project, budget_preflight=preflight,
        )
    else:  # pragma: no cover - real LLM path, exercised in the pilot not unit tests
        from startd8.stakeholder_panel.panel import StakeholderPanel

        panel = StakeholderPanel(
            roster, project_root=project_root, model_spec=model,
            cost_tracker=cost_tracker, cost_project=scope_project, budget_preflight=preflight,
        )

    try:
        import asyncio

        answers = asyncio.run(panel.ask_all(question, cap=cap))
        answer_dicts = [a.to_dict() if hasattr(a, "to_dict") else dict(a) for a in answers]
        # Partial-failure (FR-6): a "deferred"/"unavailable" answer means not every persona spent.
        statuses = {d.get("grounding") for d in answer_dicts}
        status = "partial" if {"deferred", "unavailable"} & statuses else "completed"
        store.mark_complete(run_key, panel.session_id, now=now)
        return RunResult(panel.session_id, answer_dicts, status, run_key)
    finally:
        try:
            panel.close()
        except Exception:  # pragma: no cover
            pass
