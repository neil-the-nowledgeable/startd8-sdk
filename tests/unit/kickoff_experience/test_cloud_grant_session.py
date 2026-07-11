"""M2 — grant-capable cloud build + session-creation under the FR-14 trust chain (R1-S1/S7, FR-15).

On a grant-capable cloud build, opening a chat session (the pre-message surface) requires the full
trust chain — api-key ∧ Origin ∈ configured ∧ a live grant — and CONSUMES one use. A missing factor →
"unavailable" with no session created and no use spent.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.cloud_grant import GrantStore, GrantTarget  # noqa: E402
from startd8.kickoff_experience.proposals import ProposalBuffer  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

KEY = "consumer-key"
ORIGIN = "https://cloud.example.com"
DEP, PROJ = "dep-1", "proj"


class _FakeChat:
    def __init__(self):
        self.buffer = ProposalBuffer()
        self.session = type("S", (), {"messages": []})()


def _issue(store, *, capability="chat-write", uses=1):
    return store.issue(GrantTarget(DEP, PROJ, capability), uses=uses,
                       ttl_seconds=900.0, now=time.time(), issued_by="operator:test")


def _app(tmp_path, store, *, agent=True):
    return build_kickoff_app(
        tmp_path, cloud=True, api_key=KEY,
        grant_store=store, deployment_id=DEP, project_id=PROJ,
        cloud_origins=frozenset({ORIGIN}),
        chat_factory=(lambda: _FakeChat()) if agent else None,
    )


def _open(client, *, key=KEY, origin=ORIGIN):
    h = {}
    if key is not None:
        h["x-api-key"] = key
    if origin is not None:
        h["origin"] = origin
    return client.get("/concierge/chat", headers=h)


def _created(resp) -> bool:
    return resp.status_code == 200 and "/concierge/chat/message" in resp.text


def _unavailable(resp) -> bool:
    return "unavailable on cloud" in resp.text.lower()


def test_full_trust_chain_creates_session_and_consumes_the_grant(tmp_path):
    store = GrantStore()
    _issue(store, uses=1)
    c = TestClient(_app(tmp_path, store))
    assert _created(_open(c)), "valid api-key + Origin + live grant → session created"
    # the single use was consumed → a second open is denied
    assert _unavailable(_open(c)), "1-use grant consumed at session creation → second open denied"


def test_missing_api_key_denies_and_does_not_consume(tmp_path):
    store = GrantStore()
    _issue(store, uses=1)
    c = TestClient(_app(tmp_path, store))
    assert _unavailable(_open(c, key=None)), "no api-key → unavailable"
    # the grant was NOT spent (trust chain short-circuits before consume) → now a full open succeeds
    assert _created(_open(c)), "grant untouched by the keyless attempt"


def test_wrong_origin_denies(tmp_path):
    store = GrantStore()
    _issue(store, uses=1)
    c = TestClient(_app(tmp_path, store))
    assert _unavailable(_open(c, origin="https://evil.example.com"))


def test_no_grant_issued_denies(tmp_path):
    c = TestClient(_app(tmp_path, GrantStore()))   # grant-capable build, but no grant in the store
    assert _unavailable(_open(c))


def test_grant_for_a_different_capability_denies(tmp_path):
    store = GrantStore()
    _issue(store, capability="read-metrics", uses=1)   # not "chat-write"
    c = TestClient(_app(tmp_path, store))
    assert _unavailable(_open(c))


def test_cloud_without_grant_store_is_unchanged(tmp_path):
    # No grant store → the M1 strict cloud posture (byte-preserved): chat page unavailable.
    c = TestClient(build_kickoff_app(tmp_path, cloud=True))
    assert _unavailable(c.get("/concierge/chat"))
