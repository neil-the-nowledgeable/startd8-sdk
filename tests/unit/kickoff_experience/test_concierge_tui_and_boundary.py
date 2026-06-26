"""M-CM4 (TUI driver), M-CM6 (read-only floor regression guard), M-CM7 (first-run journey)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience.concierge_apply import ConciergeWriteCode
from startd8.kickoff_experience.tui_concierge import CONFIRM_UNAVAILABLE, run_concierge


# --- M-CM4: TUI driver -------------------------------------------------------------------------

def _runner(answers):
    """A confirm/prompt pair driven by a scripted list of answers."""
    seq = list(answers)

    def confirm(_msg):
        return seq.pop(0)

    def prompt(_msg):
        return seq.pop(0)

    return confirm, prompt


def test_tui_instantiate_then_friction(tmp_path: Path) -> None:
    lines: list = []
    # confirm instantiate=True, confirm friction=True, then 3 friction prompts.
    confirm, prompt = _runner([True, True, "grammar rejected PRD", "reformat", "F-4 path"])
    res = run_concierge(str(tmp_path), confirm=confirm, prompt=prompt, emit_line=lines.append)
    assert res.instantiate == ConciergeWriteCode.OK
    assert res.friction == ConciergeWriteCode.OK
    assert (tmp_path / "docs" / "kickoff" / "inputs" / "conventions.yaml").exists()
    assert (tmp_path / "concierge-friction.jsonl").exists()


def test_tui_fails_closed_when_confirm_unavailable(tmp_path: Path) -> None:
    # questionary returns None on a non-TTY/interrupt → no write.
    confirm, prompt = _runner([None, None])
    res = run_concierge(str(tmp_path), confirm=confirm, prompt=prompt, emit_line=lambda _l: None)
    assert res.instantiate == CONFIRM_UNAVAILABLE
    assert not (tmp_path / "docs" / "kickoff" / "inputs").exists()  # nothing written


def test_tui_decline_instantiate(tmp_path: Path) -> None:
    confirm, prompt = _runner([False, False])  # decline both
    res = run_concierge(str(tmp_path), confirm=confirm, prompt=prompt, emit_line=lambda _l: None)
    assert res.instantiate is None and res.friction is None
    assert not (tmp_path / "docs" / "kickoff" / "inputs").exists()


def test_tui_friction_validation(tmp_path: Path) -> None:
    # Package already there is irrelevant; decline instantiate, confirm friction, blank field.
    confirm, prompt = _runner([False, True, "", "x", "y"])
    res = run_concierge(str(tmp_path), confirm=confirm, prompt=prompt, emit_line=lambda _l: None)
    assert res.friction == ConciergeWriteCode.MISSING_REQUIRED_FIELD
    assert not (tmp_path / "concierge-friction.jsonl").exists()


# --- M-CM6: read-only floor regression guard (R1-S5) -------------------------------------------

def test_kickoff_registry_has_no_write_tool() -> None:
    from startd8.kickoff_experience.chat import build_kickoff_registry

    names = build_kickoff_registry("/tmp/x").names()
    assert names == {"survey", "assess", "field_states"}
    for write_name in ("instantiate-kickoff", "log-friction", "derive-contract",
                       "instantiate", "friction", "apply"):
        assert write_name not in names


def test_mcp_state_tool_is_not_the_concierge_aggregator(tmp_path: Path) -> None:
    # FR-CM-9 / R1-F7: the MCP read payload is the bare kickoff state, NOT build_concierge_view
    # (which carries write-affordance metadata like instantiate_offer + friction_form).
    from startd8.kickoff_experience import kickoff_state_tool

    payload = kickoff_state_tool(str(tmp_path))
    assert "instantiate_offer" not in payload
    assert "friction_form" not in payload
    assert payload.get("action") != "concierge_view"


# --- M-CM7: package-less first-run journey (R3-F3) ---------------------------------------------

def test_package_less_first_run_journey() -> None:
    pytest.importorskip("fastapi")
    import re
    import tempfile

    from fastapi.testclient import TestClient

    from startd8.kickoff_experience.web import build_kickoff_app

    # A real (non-symlinked) package-less root so the safe-writer accepts writes.
    root = Path(tempfile.mkdtemp()).resolve()
    client = TestClient(build_kickoff_app(root), headers={"host": "127.0.0.1"})

    # 1. serve succeeds (overview 200) even with no kickoff package
    assert client.get("/").status_code == 200
    # 2. Concierge offers instantiate (package missing)
    cj = client.get("/concierge.json").json()
    assert cj["instantiate_offer"]["package_state"] == "missing"
    # 3. preview writes nothing
    assert client.post("/concierge/instantiate/preview", data={"posture": "prototype"}).json()["ok"]
    assert not (root / "docs" / "kickoff" / "inputs").exists()
    # 4. apply instantiate
    html = client.get("/concierge").text
    csrf = re.search(r"name='csrf' value='([^']+)'", html).group(1)
    tokens = re.findall(r"name='intent' value='([^']+)'", html)
    r = client.post("/concierge/instantiate",
                    data={"posture": "prototype", "csrf": csrf, "intent": tokens[0]})
    assert r.json()["package_state"] == "complete"
    # 5. refreshed state no longer offers package creation
    assert client.get("/concierge.json").json()["instantiate_offer"]["needed"] is False
    # 6. log friction
    r2 = client.post("/concierge/friction", data={
        "friction": "grammar gap", "what_happened": "x", "implication": "y",
        "csrf": csrf, "intent": tokens[1]})
    assert r2.json()["ok"]
    assert (root / "concierge-friction.jsonl").exists()
