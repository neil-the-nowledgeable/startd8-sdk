"""FR-WM2-5d **softened for local single-user** (`--mirror-cockpit`): a local web chat turn persists
the *redacted* FR-1 snapshot + the VIPP inbox so the agentic cockpit's Assistant/Proposals tabs
populate. The strict RAM-only/no-disk contract still holds by **default** (library callers) and under
`--cloud` (hosted) — proven here: no chat artifact on disk unless the local mirror is explicitly on.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience import session_snapshot as ss  # noqa: E402
from startd8.kickoff_experience.proposals import ProposalBuffer, ProposedAction  # noqa: E402
from startd8.kickoff_experience.vipp_seam import inbox_path  # noqa: E402
from startd8.kickoff_experience.web import build_kickoff_app  # noqa: E402

PLANTED_SECRET = "sk-ant-ABCDEFGH1234567890abcdefghij"


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text
        self.stop_reason = "completed"   # not in _CHAT_STOP_CODE → success path
        self.turns = 1
        self.total_tokens = 5
        self.total_cost_usd = 0.001


class _Session:
    def __init__(self) -> None:
        self.messages: list = []
        self.total_input_tokens = 10
        self.total_output_tokens = 5
        self.total_tokens = 15
        self.total_cost_usd = 0.001
        self.agent = type("A", (), {"model": "claude-x"})()


class _MirrorChat:
    """A fake agentic chat WITH a real session (so the snapshot has turns) + a proposal per turn."""

    def __init__(self) -> None:
        self.buffer = ProposalBuffer()
        self.session = _Session()
        self.agentic = True
        self.red_carpet = False

    async def ask(self, message: str):
        self.session.messages.append({"role": "user", "content": message})
        self.session.messages.append(
            {"role": "assistant", "content": [
                {"type": "text", "text": f"my key is {PLANTED_SECRET}; I recommend capturing tz=UTC"}]}
        )
        self.buffer.add(ProposedAction(
            "capture", {"value_path": "conventions.tz", "value": "UTC"}, id="P-1"))
        return _Result(f"echo {message}")

    def cost_line(self, result: _Result) -> str:
        return f"cost={result.total_cost_usd}"


def _client(tmp_path: Path, *, mirror: bool, cloud: bool = False) -> TestClient:
    factory = None if cloud else (lambda: _MirrorChat())
    return TestClient(
        build_kickoff_app(tmp_path, chat_factory=factory, mirror_cockpit=mirror, cloud=cloud),
        headers={"host": "127.0.0.1:8000"},
    )


def _drive_turn(client: TestClient):
    client.get("/concierge/chat")   # sets the httponly kickoff_chat + kickoff_csrf cookies
    return client.post("/concierge/chat/message", data={"message": "what's missing?"})


def test_mirror_on_persists_redacted_snapshot_and_inbox(tmp_path: Path) -> None:
    client = _client(tmp_path, mirror=True)
    r = _drive_turn(client)
    assert r.json()["ok"] is True

    snap = ss.snapshot_path(tmp_path)
    assert snap.is_file(), "mirror on → the FR-1 snapshot is written (Assistant tab)"
    assert inbox_path(tmp_path).is_file(), "mirror on → the VIPP inbox is serialized (Proposals tab)"
    # Redaction holds: the planted secret never reaches the persisted snapshot bytes.
    assert PLANTED_SECRET not in snap.read_text(encoding="utf-8")


def test_mirror_off_writes_nothing(tmp_path: Path) -> None:
    # Default library posture stays strict (FR-WM2-5d): a turn leaves NO chat artifact on disk.
    client = _client(tmp_path, mirror=False)
    r = _drive_turn(client)
    assert r.json()["ok"] is True
    assert not ss.snapshot_path(tmp_path).exists()
    assert not inbox_path(tmp_path).exists()


def test_cloud_stays_strict_no_mirror(tmp_path: Path) -> None:
    # --cloud disables chat AND force-clears mirror_cockpit: the message is refused and nothing persists.
    client = _client(tmp_path, mirror=True, cloud=True)
    client.get("/concierge/chat")
    client.post("/concierge/chat/message", data={"message": "x"})
    assert not ss.snapshot_path(tmp_path).exists()
    assert not inbox_path(tmp_path).exists()
