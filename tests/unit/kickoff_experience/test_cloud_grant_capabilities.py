"""FR-E18 — generalize the grant beyond chat-write: `capture` and `instantiate` are grantable on
cloud via the SAME trust chain (api-key ∧ Origin ∧ grant, one use consumed). A grant for one
capability never authorizes another; without a grant the write stays deferred; local is unchanged.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import GrantStore, GrantTarget  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

KEY = "consumer-key"
ORIGIN = "https://cloud.example.com"
DEP, PROJ, T0 = "dep-1", "proj", 1_000_000.0
HDRS = {"x-api-key": KEY, "origin": ORIGIN}


class _Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def _app(root, store, clock, *, cloud=True):
    return build_kickoff_app(
        root, cloud=cloud, api_key=KEY if cloud else None, grant_store=store,
        deployment_id=DEP, project_id=PROJ, cloud_origins=frozenset({ORIGIN}), grant_clock=clock,
    )


def _issue(store, capability, *, uses=1):
    store.issue(GrantTarget(DEP, PROJ, capability), uses=uses, ttl_seconds=1000.0, now=T0,
                issued_by="operator:test")


def _capture(c):
    return c.post("/capture/apply", data={"value_path": "/x", "value": "y", "csrf": "c"}, headers=HDRS)


def _instantiate(c):
    return c.post("/concierge/instantiate",
                  data={"posture": "prototype", "csrf": "c", "intent": "i"}, headers=HDRS)


def _deferred(r) -> bool:
    return r.status_code == 501 and r.json().get("code") == "cloud_write_deferred"


# ---------------------------------------------------------------- capture


def test_capture_denied_without_a_grant(tmp_path):
    c = TestClient(_app(tmp_path, GrantStore(), _Clock()))
    assert _deferred(_capture(c))                       # cloud, no grant → deferred (unchanged)


def test_capture_allowed_under_a_capture_grant(tmp_path):
    store = GrantStore()
    _issue(store, "capture")
    c = TestClient(_app(tmp_path, store, _Clock()))
    # the grant lifts the cloud-deny → the request reaches the capture logic (NOT cloud_write_deferred)
    assert not _deferred(_capture(c))


def test_chat_grant_does_not_authorize_capture(tmp_path):
    store = GrantStore()
    _issue(store, "chat-write")                         # wrong capability
    c = TestClient(_app(tmp_path, store, _Clock()))
    assert _deferred(_capture(c))                       # capability mismatch → deferred


def test_capture_consumes_one_use(tmp_path):
    store = GrantStore()
    _issue(store, "capture", uses=1)
    c = TestClient(_app(tmp_path, store, _Clock()))
    assert not _deferred(_capture(c))                   # first spends the 1 use
    assert _deferred(_capture(c))                       # second → exhausted → deferred


# ---------------------------------------------------------------- instantiate


def test_instantiate_denied_without_a_grant(tmp_path):
    c = TestClient(_app(tmp_path, GrantStore(), _Clock()))
    assert _deferred(_instantiate(c))


def test_instantiate_allowed_under_an_instantiate_grant(tmp_path):
    store = GrantStore()
    _issue(store, "instantiate")
    c = TestClient(_app(tmp_path, store, _Clock()))
    assert not _deferred(_instantiate(c))               # grant lifts the deny (past the gate)


def test_capture_grant_does_not_authorize_instantiate(tmp_path):
    store = GrantStore()
    _issue(store, "capture")
    c = TestClient(_app(tmp_path, store, _Clock()))
    assert _deferred(_instantiate(c))                   # distinct capabilities, no cross-authorization


# ---------------------------------------------------------------- local unchanged


def test_local_capture_needs_no_grant(tmp_path):
    # cloud=False → _cloud_capability allows; the local CSRF gate applies (a bad csrf → 403, not 501).
    c = TestClient(_app(tmp_path, GrantStore(), _Clock(), cloud=False))
    r = c.post("/capture/apply", data={"value_path": "/x", "value": "y", "csrf": "bogus"})
    assert r.status_code != 501                         # never cloud-deferred locally
