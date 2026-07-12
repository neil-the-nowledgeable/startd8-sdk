"""FR-E19 — served-surface auth CONFORMANCE (the shared *contract*, not shared code).

See `docs/design/kickoff/ADR_E19_SURFACE_AUTH.md`. The three served surfaces — kickoff `web.py` (cloud),
`stakeholder_run_server` (household), `consultation/serve` (loopback) — have **deliberately divergent**
auth semantics (empty-Origin policy, `localhost` handling, replay model), so a shared middleware is
rejected. Exactly ONE invariant is universal and guarded here:

    a credential comparison is CONSTANT-TIME, and a wrong/absent credential is rejected.

This is the drift guard: if any surface swaps `compare_digest` for `==`, or stops rejecting a bad
credential, this fails — without imposing a lowest-common-denominator abstraction on three surfaces
whose *policies* should differ.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.consultation import serve as consult_serve  # noqa: E402
from startd8.kickoff_experience import stakeholder_run_server as stk  # noqa: E402
from startd8.kickoff_experience.cloud_grant import (  # noqa: E402
    GrantStore,
    GrantTarget,
    TrustChainInputs,
    evaluate_trust_chain,
)

pytestmark = pytest.mark.unit

# The universal invariant: every surface's credential comparator must be constant-time. We assert it at
# the source level so a regression to `==` is caught even if a behavioral test would still pass by luck.
_CONSTANT_TIME_SURFACES = {
    "kickoff.cloud_grant.evaluate_trust_chain": evaluate_trust_chain,
    "consult.serve._token_ok": consult_serve._token_ok,
    "stakeholder._authorize": stk._authorize,
}


@pytest.mark.parametrize("name,fn", list(_CONSTANT_TIME_SURFACES.items()))
def test_surface_uses_constant_time_credential_compare(name, fn):
    src = inspect.getsource(fn)
    assert "compare_digest" in src, (
        f"{name} must compare its credential with a constant-time comparator (compare_digest), "
        f"not `==` — see ADR_E19_SURFACE_AUTH.md"
    )


def test_consult_rejects_wrong_and_absent_token():
    # consult: per-run token, constant-time (_token_ok is the shared-contract entry).
    assert consult_serve._token_ok("secret", "secret") is True
    assert consult_serve._token_ok("wrong", "secret") is False
    assert consult_serve._token_ok(None, "secret") is False
    assert consult_serve._token_ok("", "secret") is False


def test_kickoff_rejects_wrong_and_absent_api_key():
    # kickoff cloud: the trust chain's api-key factor rejects a wrong/absent key BEFORE the grant.
    store = GrantStore()
    target = GrantTarget("dep", "proj", "chat-write")
    store.issue(target, uses=1, ttl_seconds=1000, now=0.0, issued_by="op")

    def _decide(presented):
        inputs = TrustChainInputs(api_key_expected="right-key", api_key_presented=presented,
                                  allowed_origins=frozenset({"https://x"}), origin_presented="https://x")
        return evaluate_trust_chain(store, target, inputs, now=1.0)

    assert _decide("right-key").allowed is True
    assert _decide("wrong-key").allowed is False
    assert _decide(None).allowed is False


def test_divergence_is_intentional_not_accidental():
    # A guard against a naive "these look the same, unify them" refactor: the two _host_ok functions
    # have OPPOSITE localhost behavior on purpose (see the ADR). If someone unifies them, this catches it.
    from startd8.kickoff_experience import web as kickoff_web

    assert kickoff_web._host_ok("localhost:8080") is True          # cloud surface accepts localhost
    assert consult_serve._host_ok("localhost:8080", 8080) is False  # loopback surface rejects it
    assert consult_serve._host_ok("127.0.0.1:8080", 8080) is True
