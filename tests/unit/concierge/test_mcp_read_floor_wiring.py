"""FR-7 — the MCP concierge path routes READ actions through the structural read floor.

Both MCP servers dispatch concierge via ``handle_concierge_tool``. FR-7 requires that READ actions
(``survey``/``assess``) additionally route through ``handle_concierge_read`` so read-only is
*structural* (a write verb is rejected BEFORE dispatch, not merely preview-incidental), while write
actions keep returning a preview ``WritePlan`` (MCP never writes — the CLI is the only applier, OQ-7).

The MCP server modules import ``mcp.server.fastmcp`` which is absent in this venv, so they cannot be
imported here. We therefore verify the wiring at two levels that DO collect:

  1. a source-level check that BOTH server modules gate reads through ``handle_concierge_read``;
  2. the behavioral guarantees the wiring relies on — the floor rejects a write verb, and the MCP
     write path (``handle_concierge_tool``) returns a preview plan that touches no disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.concierge import ConciergeError, handle_concierge_read, handle_concierge_tool

_MCP_DIR = Path(__file__).resolve().parents[3] / "mcp" / "startd8-mcp-builder"
_SERVER_FILES = [
    _MCP_DIR / "startd8_mcp.py",
    _MCP_DIR / "startd8_mcp_server" / "server.py",
]


@pytest.mark.parametrize("server_file", _SERVER_FILES, ids=lambda p: p.name)
def test_mcp_server_routes_reads_through_the_floor(server_file):
    """Structural: each server's concierge dispatch gates READ actions through the read floor."""
    src = server_file.read_text(encoding="utf-8")
    assert "handle_concierge_read" in src, f"{server_file.name}: reads must route via the floor (FR-7)"
    assert "READ_ACTIONS" in src, f"{server_file.name}: read/write split must key on READ_ACTIONS"
    # Writes still go through handle_concierge_tool (preview WritePlan; MCP never writes).
    assert "handle_concierge_tool" in src, f"{server_file.name}: write path must keep handle_concierge_tool"
    # The gate: `if action in READ_ACTIONS:` selects the read floor.
    assert "if action in READ_ACTIONS" in src, f"{server_file.name}: reads must be gated on READ_ACTIONS"


def test_read_floor_rejects_a_write_verb_before_dispatch(tmp_path):
    """The floor is structural: a write verb over the read path is refused, not previewed."""
    for verb in ("instantiate", "instantiate-kickoff", "log-friction", "derive"):
        with pytest.raises(ConciergeError) as exc:
            handle_concierge_read(verb, str(tmp_path))
        assert "read-only" in str(exc.value)


def test_read_action_flows_through_the_floor(tmp_path):
    out = handle_concierge_read("assess", str(tmp_path))
    assert out["action"] == "assess" and out["schema_version"] >= 1


def test_mcp_write_action_is_preview_only_and_writes_nothing(tmp_path):
    """The MCP write path returns a preview WritePlan and touches no disk (OQ-7)."""
    before = {p for p in tmp_path.rglob("*")}
    plan = handle_concierge_tool("instantiate", str(tmp_path), posture="prototype")
    # A preview plan: it names the intended writes but performs none.
    assert "writes" in plan, "instantiate must return a WritePlan (preview)"
    after = {p for p in tmp_path.rglob("*")}
    assert before == after, "MCP write path must not touch disk — preview only"
