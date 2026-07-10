"""The startd8_kickoff_status MCP tool — the Digital Project Workbook oracle over MCP (read-only, $0).

Pins: the tool exists + is annotated read-only/non-destructive, and its handler returns the
`startd8.kickoff.status.v1` JSON payload without writing to disk.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import startd8_mcp


def test_kickoff_status_tool_exists_and_is_read_only():
    assert hasattr(startd8_mcp, "startd8_kickoff_status")
    tm = getattr(startd8_mcp.mcp, "_tool_manager", None)
    tools = getattr(tm, "_tools", {})
    assert "startd8_kickoff_status" in tools
    tool = tools["startd8_kickoff_status"]
    ann = getattr(tool, "annotations", None) or {}
    # annotations may be a pydantic model or dict depending on FastMCP version
    get = (lambda k: getattr(ann, k, None)) if not isinstance(ann, dict) else ann.get
    assert get("readOnlyHint") is True and get("destructiveHint") is False


def test_kickoff_status_handler_returns_v1_json_and_writes_nothing():
    root = Path(tempfile.mkdtemp())
    env = {
        "kind": "vipp-proposal-envelope", "protocol_version": "1.0", "project_id": "p",
        "envelope_seq": 1, "generated_at": "t", "content_checksum": "",
        "proposals": [{"kind": "capture", "params": {"value_path": "a.b"}, "id": "P-9", "base_sha": None}],
    }
    ip = root / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env), encoding="utf-8")
    before = {p.name for p in root.rglob("*")}

    out = asyncio.run(
        startd8_mcp.startd8_kickoff_status(startd8_mcp.KickoffStatusInput(project_root=str(root)))
    )
    d = json.loads(out)
    assert d["schema"] == "startd8.kickoff.status.v1"
    assert d["proposals"][0]["id"] == "P-9"
    # read-only: nothing new written to disk
    assert {p.name for p in root.rglob("*")} == before
