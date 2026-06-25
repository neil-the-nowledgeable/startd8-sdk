"""Unit tests for R3-M4/M5 frontend HTTP contract + gate + bonus (fleet.frontend_contract) — no http.

Pins the journey route contract (§1), the gate stage semantics (§4 — BOOT/ROUTES/JOURNEY blocking,
ORCHESTRATION advisory), substitution on failure, and the M5 bonus cap (additive, never rank-flips).
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.fleet import frontend_contract as FC
from startd8.benchmark_matrix.fleet import journey as J

pytestmark = pytest.mark.unit


def test_six_journey_routes_with_statuses():
    paths = [(r.method, r.path) for r in FC.JOURNEY_ROUTES]
    assert paths == [("GET", "/"), ("GET", "/product/{id}"), ("POST", "/setCurrency"),
                     ("POST", "/cart"), ("GET", "/cart"), ("POST", "/cart/checkout")]
    # the cart/currency POSTs redirect (302); GETs + checkout return 200
    assert FC.ROUTE_BY_KEY[("POST", "/setCurrency")].ok_status == 302
    assert FC.ROUTE_BY_KEY[("POST", "/cart")].ok_status == 302
    assert FC.ROUTE_BY_KEY[("POST", "/cart/checkout")].ok_status == 200
    # malformed add/checkout must 4xx, not 200/500
    assert FC.ROUTE_BY_KEY[("POST", "/cart/checkout")].bad_status == 422


def test_checkout_route_fans_out_to_checkout_service():
    assert "checkoutservice" in FC.ROUTE_BY_KEY[("POST", "/cart/checkout")].fanout


def test_blocking_stages_exclude_orchestration():
    assert FC.GateStage.ORCHESTRATION not in FC.BLOCKING_STAGES
    assert set(FC.BLOCKING_STAGES) == {FC.GateStage.BOOT, FC.GateStage.ROUTES, FC.GateStage.JOURNEY}


def test_verdict_pass_mounts_generated():
    v = FC.make_verdict({s: True for s in FC.GateStage})
    assert v.passed and v.mounted == "generated" and v.failing_stage is None


def test_verdict_fail_substitutes_canonical_at_first_blocking_stage():
    # JOURNEY fails (the decisive stage); BOOT/ROUTES passed → substitute, name the failing stage.
    results = {FC.GateStage.BOOT: True, FC.GateStage.ROUTES: True,
               FC.GateStage.JOURNEY: False, FC.GateStage.ORCHESTRATION: True}
    v = FC.make_verdict(results)
    assert not v.passed and v.mounted == "canonical-substituted" and v.failing_stage == "journey"


def test_orchestration_failure_does_not_fail_the_gate():
    # advisory stage red, all blocking green → still PASS (it only reduces bonus).
    results = {FC.GateStage.BOOT: True, FC.GateStage.ROUTES: True,
               FC.GateStage.JOURNEY: True, FC.GateStage.ORCHESTRATION: False}
    assert FC.make_verdict(results).passed


def test_bonus_is_zero_unless_gate_passed():
    fail = FC.FrontendVerdict(False, "journey", mounted="canonical-substituted")
    assert FC.frontend_bonus(fail, orchestration_fidelity=1.0) == 0.0


def test_bonus_capped_and_additive():
    ok = FC.FrontendVerdict(True, None, mounted="generated")
    assert FC.frontend_bonus(ok, 1.0) == FC.FRONTEND_BONUS_CAP   # full fidelity -> the cap
    assert FC.frontend_bonus(ok, 0.5) == pytest.approx(FC.FRONTEND_BONUS_CAP * 0.5)
    # the bonus NEVER exceeds the cap (even at >1 fidelity it's clamped) — it is a separate tie-break
    # column folded onto backend_score, not part of the rank key, so it can't flip the backend ranking.
    assert FC.frontend_bonus(ok, 99.0) == FC.FRONTEND_BONUS_CAP
    assert 0.0 < FC.FRONTEND_BONUS_CAP <= 0.10


def test_checkout_form_encodes_canonical_payload():
    form = FC.checkout_form(now_year=2026)
    assert set(form) == set(FC.ROUTE_BY_KEY[("POST", "/cart/checkout")].form_fields)
    assert form["credit_card_number"] == "4111111111111111"  # Luhn-valid
    assert int(form["credit_card_expiration_year"]) == 2031   # now_year + 5 (future)
    assert form["email"] == J.canonical_checkout_payload(now_year=2026).email
