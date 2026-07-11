"""M3b — the WRITE half of chat-write under a grant: proposal-apply + the redacted cockpit mirror.

`chat/confirm` (proposal-apply) is enabled on cloud under a grant via the SAME per-turn revalidation
(no re-consume) and reaches the UNCHANGED `apply_proposal` safe-writer (FR-16). The redacted cockpit
mirror is allowed for a grant-authorized cloud session — still redacted (FR-9), so no secret hits disk.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience import session_snapshot as ss  # noqa: E402
from startd8.kickoff_experience.cloud_grant import GrantStore, GrantTarget  # noqa: E402
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

KEY = "consumer-key"
ORIGIN = "https://cloud.example.com"
DEP, PROJ = "dep-1", "proj"
T0 = 1_000_000.0
SECRET = "sk-ant-ABCDEFGH1234567890abcdefghij"
HDRS = {"x-api-key": KEY, "origin": ORIGIN}


@dataclass
class _Result:
    text: str = "ok"
    stop_reason: str = "completed"
    turns: int = 1
    total_tokens: int = 5
    total_cost_usd: float = 0.001


class _Session:
    def __init__(self):
        self.messages = []
        self.total_input_tokens = 5
        self.total_output_tokens = 3
        self.total_tokens = 8
        self.total_cost_usd = 0.001
        self.agent = type("A", (), {"model": "m"})()


class _FakeChat:
    def __init__(self):
        self.buffer = ProposalBuffer()
        self.session = _Session()

    async def ask(self, message: str) -> _Result:
        self.session.messages.append({"role": "user", "content": message})
        self.session.messages.append(
            {"role": "assistant", "content": [{"type": "text", "text": f"my key is {SECRET}"}]})
        self.buffer.add(ProposedAction("friction",
                        {"friction": "f", "what_happened": "w", "implication": "i"}, id="p1"))
        return _Result()

    def cost_line(self, result) -> str:
        return "cost=0.001"


class _Clock:
    def __init__(self, t=T0):
        self.t = t

    def __call__(self):
        return self.t


def _app(root, store, clock):
    return build_kickoff_app(
        root, cloud=True, api_key=KEY, grant_store=store, deployment_id=DEP, project_id=PROJ,
        cloud_origins=frozenset({ORIGIN}), grant_clock=clock, chat_factory=lambda: _FakeChat(),
    )


def _issue(store, *, uses=1, ttl=1000.0, now=T0):
    return store.issue(GrantTarget(DEP, PROJ, "chat-write"), uses=uses,
                       ttl_seconds=ttl, now=now, issued_by="operator:test")


def _open(c):
    return c.get("/concierge/chat", headers=HDRS)


def _turn(c, msg="hi"):
    return c.post("/concierge/chat/message", data={"message": msg}, headers=HDRS)


def _confirm(c, pid="p1"):
    return c.post("/concierge/chat/confirm", data={"proposal_id": pid, "csrf": "x"}, headers=HDRS)


def test_confirm_under_grant_reaches_the_safe_writer(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    _issue(store)
    c = TestClient(_app(tmp_path, store, clock))
    assert _open(c).status_code == 200
    _turn(c)                                    # proposal p1 now pending
    r = _confirm(c)
    # the grant lifted the cloud-deny → confirm reached apply_proposal (NOT cloud_write_deferred)
    assert r.status_code != 501
    assert r.json().get("code") != "cloud_write_deferred"


def test_confirm_denied_after_grant_expiry(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    _issue(store, ttl=100.0)
    c = TestClient(_app(tmp_path, store, clock))
    clock.t = T0 + 50
    _open(c)
    _turn(c)
    clock.t = T0 + 101                          # grant expired
    r = _confirm(c)
    assert r.status_code == 501 and r.json()["code"] == "cloud_write_deferred"


def test_confirm_on_cloud_without_grant_is_deferred(tmp_path):
    # grant-capable build, but no grant issued → confirm (a write) stays strict.
    c = TestClient(_app(tmp_path, GrantStore(), _Clock(T0)))
    r = _confirm(c)
    assert r.status_code == 501 and r.json()["code"] == "cloud_write_deferred"


def test_grant_session_mirror_is_written_and_redacted(tmp_path):
    store, clock = GrantStore(), _Clock(T0)
    _issue(store)
    c = TestClient(_app(tmp_path, store, clock))
    assert _open(c).status_code == 200
    clock.t = T0 + 1
    assert _turn(c).json()["ok"] is True
    # the redacted mirror is written under the grant (cloud) …
    snap = ss.snapshot_path(tmp_path)
    assert snap.is_file(), "a grant-authorized cloud session mirrors to the cockpit store"
    # … and the planted secret never reaches disk (FR-9 redaction still holds on cloud)
    assert SECRET not in snap.read_text(encoding="utf-8")


def test_no_grant_no_mirror(tmp_path):
    # cloud + no grant store → no chat, no mirror artifact (hosted stays strict).
    c = TestClient(build_kickoff_app(tmp_path, cloud=True))
    c.get("/concierge/chat")
    assert not ss.snapshot_path(tmp_path).exists()
