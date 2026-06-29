"""Red Carpet Treatment — the agentic interview loop (stage-aware chat + the propose-only REPL).

The conductor's interactive brain: a stage-aware chat that can propose EVERY input kind
(schema/manifest/value), grounded in the `red_carpet_state` read tool, and a pure REPL driver that
turns agent proposals into human-confirmed applies.
"""

from __future__ import annotations

from pathlib import Path

from startd8.kickoff_experience.chat import (
    RED_CARPET_BANNER,
    RED_CARPET_SYSTEM_PROMPT,
    _PROPOSE_SCHEMA,
    build_kickoff_registry,
    handle_kickoff_read,
    new_red_carpet_chat,
)
from startd8.kickoff_experience.red_carpet import run_red_carpet_repl


class _StubAgent:  # AgenticSession construction only stores the agent/registry/config
    def supports_tool_use(self) -> bool:
        return True


# --- the agent can now propose every input kind (closing the N1/N2 schema-enum gap) ---------------

def test_propose_schema_enum_covers_all_kinds() -> None:
    enum = _PROPOSE_SCHEMA["properties"]["kind"]["enum"]
    assert set(enum) == {"instantiate", "friction", "capture", "schema", "manifest", "brief"}
    # the schema/manifest params are declared so the agent can fill them
    props = _PROPOSE_SCHEMA["properties"]
    assert "brief" in props and "source" in props and "source_label" in props


# --- the stage-aware read tool --------------------------------------------------------------------

def test_red_carpet_state_is_a_read_tool(tmp_path: Path) -> None:
    payload = handle_kickoff_read("red_carpet_state", tmp_path)
    assert payload["next_stage"] == "data_model" and payload["cascade_offerable"] is False
    assert [s["key"] for s in payload["stages"]][0] == "data_model"


def test_red_carpet_registry_is_stage_aware_and_read_only(tmp_path: Path) -> None:
    reg = build_kickoff_registry(tmp_path, proposal_sink=lambda _p: "ok", red_carpet=True)
    names = set(reg._tools)
    assert "red_carpet_state" in names and "propose_action" in names
    assert reg.allow_effect_classes == {"read"}                 # still the no-loop-write floor
    assert all(s.effect_class == "read" for s in reg._tools.values())
    # the default (non-RCT) registry does NOT carry the staged tool
    assert "red_carpet_state" not in set(build_kickoff_registry(tmp_path)._tools)


def test_new_red_carpet_chat_constructs_stage_aware(tmp_path: Path) -> None:
    chat = new_red_carpet_chat(_StubAgent(), tmp_path)
    assert chat.red_carpet is True and chat.buffer is not None
    assert chat.banner() == RED_CARPET_BANNER
    assert chat.session.system_prompt == RED_CARPET_SYSTEM_PROMPT
    assert "red_carpet_state" in set(chat.session.registry._tools)


# --- the pure REPL driver: propose → human confirm → apply ----------------------------------------

class _Result:
    def __init__(self, text: str) -> None:
        self.text = text


def test_repl_routes_each_proposal_to_the_host(monkeypatch) -> None:
    # One turn that yields two proposals, then quit. on_proposal must see both; the loop never applies.
    seen = []
    proposals = [{"id": "p1"}, {"id": "p2"}]
    inputs = iter(["build me a todo app", ""])   # one message, then empty → quit
    emitted = []

    turns = run_red_carpet_repl(
        banner="BANNER",
        ask_sync=lambda m: _Result(f"echo: {m}"),
        read_input=lambda _p: next(inputs, None),
        emit_line=emitted.append,
        pending=lambda: proposals if not seen else [],   # drained after the first turn
        on_proposal=lambda a: seen.append(a["id"]) or f"applied {a['id']}",
        render_state=lambda: emitted.append("STATE"),
    )
    assert turns == 1
    assert seen == ["p1", "p2"]                  # both proposals routed to the host
    assert "BANNER" in emitted and "echo: build me a todo app" in emitted
    assert emitted.count("STATE") == 2           # rendered at start and after the turn
