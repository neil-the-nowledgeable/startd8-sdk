"""Unit tests for the Phase 2 M0 core (stakeholder-panel run orchestration + guardrails)."""
from __future__ import annotations

import pytest

from startd8.costs.models import CostPeriod
from startd8.kickoff_experience.stakeholder_run import (
    BudgetNotConfiguredError,
    DryRun,
    IdempotencyStore,
    RunKeyMismatchError,
    derive_run_key,
    dry_run,
    ensure_blocking_budget,
    ensure_daily_ceiling,
    estimate_cost_per_question,
    execute_run,
    roster_version,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- fakes


class _P:
    def __init__(self, role_id, display_name=""):
        self.role_id = role_id
        self.display_name = display_name


class _Roster:
    def __init__(self, personas):
        self.personas = personas

    def to_dict(self):
        return {"personas": [{"role_id": p.role_id, "display_name": p.display_name} for p in self.personas]}


class _Pricing:
    def __init__(self, inp, out):
        self._p = type("MP", (), {"input_cost_per_million": inp, "output_cost_per_million": out})()

    def get_pricing(self, model):
        return self._p if model != "unknown:model" else None


class _Budget:
    def __init__(self, block, scope):
        self.block_on_exceed = block
        self.scope_project = scope


class _Manager:
    def __init__(self, budgets):
        self._b = budgets

    def list_budgets(self, active_only=True):
        return self._b


class _Answer:
    def __init__(self, role_id, grounding, text="hi"):
        self._d = {"role_id": role_id, "grounding": grounding, "text": text}

    def to_dict(self):
        return dict(self._d)


class _Panel:
    """Fake StakeholderPanel — records calls, never spends."""

    def __init__(self, roster, **kw):
        self.roster = roster
        self.kw = kw
        self.session_id = "sess-fake"
        _Panel.constructions += 1

    async def ask_all(self, question, *, cap=None, value_path=""):
        n = len(self.roster.personas) if cap is None else min(cap, len(self.roster.personas))
        return [_Answer(self.roster.personas[i].role_id, "grounded") for i in range(n)]

    def close(self):
        pass


_Panel.constructions = 0


def _blocking_manager():
    return _Manager([_Budget(True, "stakeholder-panel")])


# --------------------------------------------------------------------------- estimate / keys


def test_estimate_from_pricing():
    # 2500 input * 3.0/M + 600 output * 15.0/M = (7500 + 9000)/1e6 = 0.0165
    assert estimate_cost_per_question("m", _Pricing(3.0, 15.0)) == pytest.approx(0.0165)


def test_estimate_fallback_when_unknown():
    assert estimate_cost_per_question("unknown:model", _Pricing(3.0, 15.0)) == pytest.approx(0.02)


def test_run_key_binds_params():
    rv = "rv1"
    base = derive_run_key("q", 3, rv)
    assert derive_run_key("q", 3, rv) == base            # deterministic
    assert derive_run_key("q2", 3, rv) != base           # question
    assert derive_run_key("q", 4, rv) != base            # cap
    assert derive_run_key("q", 3, "rv2") != base         # roster


def test_roster_version_changes_with_roster():
    assert roster_version(_Roster([_P("a")])) != roster_version(_Roster([_P("b")]))
    assert roster_version(_Roster([_P("a")])) == roster_version(_Roster([_P("a")]))


def test_dry_run_math_and_key():
    r = _Roster([_P("a"), _P("b"), _P("c")])
    d = dry_run(r, "q", cap=2, model="m", pricing=_Pricing(3.0, 15.0))
    assert isinstance(d, DryRun)
    assert d.n_personas == 2                              # min(cap, len)
    assert d.estimated_cost == pytest.approx(2 * 0.0165)
    assert d.run_key == derive_run_key("q", 2, roster_version(r))


# --------------------------------------------------------------------------- idempotency


def test_idempotency_lifecycle(tmp_path):
    s = IdempotencyStore(tmp_path)
    assert s.lookup("k", "ph", now=100) is None
    s.record_start("k", "ph", now=100)
    rec = s.lookup("k", "ph", now=101)
    assert rec["status"] == "started"
    s.mark_complete("k", "sess-1", now=102)
    assert s.lookup("k", "ph", now=103)["session_id"] == "sess-1"


def test_idempotency_params_mismatch_raises(tmp_path):
    s = IdempotencyStore(tmp_path)
    s.record_start("k", "ph-A", now=100)
    with pytest.raises(RunKeyMismatchError):
        s.lookup("k", "ph-B", now=101)


def test_idempotency_ttl_expiry(tmp_path):
    s = IdempotencyStore(tmp_path, ttl_seconds=60)
    s.record_start("k", "ph", now=100)
    assert s.lookup("k", "ph", now=100 + 61) is None


# --------------------------------------------------------------------------- fail-closed budget gate


def test_ensure_blocking_budget_passes_with_blocking():
    ensure_blocking_budget(_Manager([_Budget(True, "stakeholder-panel")]))
    ensure_blocking_budget(_Manager([_Budget(True, None)]))  # global blocking budget


class _DailyBudget:
    def __init__(self, scope="stakeholder-panel"):
        self.block_on_exceed = True
        self.period = CostPeriod.DAILY
        self.scope_project = scope


class _CreatingManager:
    def __init__(self, budgets=None):
        self._b = list(budgets or [])
        self.created = []

    def list_budgets(self, active_only=True):
        return self._b

    def create_budget(self, **kw):
        b = type("B", (), {"block_on_exceed": kw["block_on_exceed"], "period": kw["period"],
                           "scope_project": kw["scope_project"]})()
        self.created.append(kw)
        self._b.append(b)
        return b


def test_ensure_daily_ceiling_creates_and_satisfies_fail_closed():
    m = _CreatingManager()
    ensure_daily_ceiling(m, limit_usd=5.0)
    assert len(m.created) == 1
    assert m.created[0]["period"] == CostPeriod.DAILY and m.created[0]["block_on_exceed"] is True
    ensure_blocking_budget(m)  # now passes — a blocking budget exists


def test_ensure_daily_ceiling_idempotent():
    m = _CreatingManager([_DailyBudget()])
    ensure_daily_ceiling(m, limit_usd=5.0)
    assert m.created == []  # reused the existing daily blocking budget


def test_ensure_blocking_budget_fail_closed():
    with pytest.raises(BudgetNotConfiguredError):
        ensure_blocking_budget(_Manager([]))                       # none configured
    with pytest.raises(BudgetNotConfiguredError):
        ensure_blocking_budget(_Manager([_Budget(False, None)]))   # non-blocking = fail-open
    with pytest.raises(BudgetNotConfiguredError):
        ensure_blocking_budget(_Manager([_Budget(True, "other")]))  # wrong scope


# --------------------------------------------------------------------------- execute_run


def _run(tmp_path, roster, question, cap, manager, run_key=None, panel_results=None):
    rk = run_key or derive_run_key(question, cap, roster_version(roster))
    return execute_run(
        roster, project_root=tmp_path, question=question, cap=cap, model="m",
        run_key=rk, budget_manager=manager, panel_factory=_Panel,
    )


def test_execute_happy_path(tmp_path):
    _Panel.constructions = 0
    r = _Roster([_P("a"), _P("b")])
    res = _run(tmp_path, r, "q", None, _blocking_manager())
    assert res.status == "completed"
    assert res.session_id == "sess-fake"
    assert [a["role_id"] for a in res.answers] == ["a", "b"]
    assert _Panel.constructions == 1


def test_execute_dedup_no_recharge(tmp_path):
    _Panel.constructions = 0
    r = _Roster([_P("a")])
    _run(tmp_path, r, "q", None, _blocking_manager())
    res2 = _run(tmp_path, r, "q", None, _blocking_manager())  # same run_key, already completed
    assert res2.status == "deduped"
    assert _Panel.constructions == 1  # the panel was NOT constructed again → no second charge


def test_execute_run_key_mismatch(tmp_path):
    r = _Roster([_P("a")])
    with pytest.raises(RunKeyMismatchError):
        _run(tmp_path, r, "q", None, _blocking_manager(), run_key="deadbeef")


def test_execute_fail_closed_no_spend(tmp_path):
    _Panel.constructions = 0
    r = _Roster([_P("a")])
    with pytest.raises(BudgetNotConfiguredError):
        _run(tmp_path, r, "q", None, _Manager([]))
    assert _Panel.constructions == 0  # refused BEFORE constructing/spending


def test_execute_forwards_cost_tracker(tmp_path):
    r = _Roster([_P("a")])
    captured = {}

    class _CapPanel(_Panel):
        def __init__(self, roster, **kw):
            super().__init__(roster, **kw)
            captured.update(kw)

    execute_run(
        r, project_root=tmp_path, question="q", cap=None, model="m",
        run_key=derive_run_key("q", None, roster_version(r)),
        budget_manager=_blocking_manager(), cost_tracker="TRACKER-SENTINEL", panel_factory=_CapPanel,
    )
    assert captured.get("cost_tracker") == "TRACKER-SENTINEL"  # FR-9: tracker reaches the panel


def test_cancel_in_flight_run(tmp_path):
    import threading
    import time

    from startd8.kickoff_experience.stakeholder_run import cancel_run

    r = _Roster([_P("a"), _P("b")])
    rk = derive_run_key("q", None, roster_version(r))

    class _SlowPanel(_Panel):
        async def ask_all(self, question, *, cap=None, value_path=""):
            import asyncio

            await asyncio.sleep(30)  # long — will be cancelled mid-flight
            return []

    out = {}

    def _worker():
        out["res"] = execute_run(
            r, project_root=tmp_path, question="q", cap=None, model="m",
            run_key=rk, budget_manager=_blocking_manager(), panel_factory=_SlowPanel,
        )

    t = threading.Thread(target=_worker)
    t.start()
    signalled = False
    for _ in range(60):  # wait until the run registers, then cancel it
        time.sleep(0.05)
        if cancel_run(rk):
            signalled = True
            break
    t.join(timeout=5)
    assert signalled
    assert out["res"].status == "cancelled"


def test_cancel_unknown_run_returns_false():
    from startd8.kickoff_experience.stakeholder_run import cancel_run

    assert cancel_run("no-such-run") is False


class _PartialPanel(_Panel):
    async def ask_all(self, question, *, cap=None, value_path=""):
        return [_Answer("a", "grounded"), _Answer("b", "deferred")]


def test_execute_partial_failure_status(tmp_path):
    r = _Roster([_P("a"), _P("b")])
    res = execute_run(
        r, project_root=tmp_path, question="q", cap=None, model="m",
        run_key=derive_run_key("q", None, roster_version(r)),
        budget_manager=_blocking_manager(), panel_factory=_PartialPanel,
    )
    assert res.status == "partial"
