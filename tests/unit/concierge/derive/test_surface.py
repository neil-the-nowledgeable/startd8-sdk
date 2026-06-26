"""Surface tests for derive-contract (Step 6): core dispatch, CLI, MCP conformance.

The CLI/dispatch paths run the contained introspection subprocess against a tmp model module.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import concierge_app
from startd8.concierge import ConciergeError, handle_concierge_tool

runner = CliRunner()

_MODELS = """
    from typing import List
    from pydantic import BaseModel
    class Child(BaseModel):
        id: str
        name: str
    class Parent(BaseModel):
        id: str
        title: str
        children: List[Child] = []
"""


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "models_demo.py").write_text(textwrap.dedent(_MODELS), encoding="utf-8")
    return tmp_path, str(src)


# ── core dispatch ─────────────────────────────────────────────────────────────

def test_dispatch_preview_returns_derivation(project):
    root, src = project
    out = handle_concierge_tool("derive-contract", root, modules=["models_demo"], pythonpath=src)
    assert out["schema_version"] == 1
    assert "unratified" in out["contract_text"]
    assert out["shape"]["entities"] == 2 and out["errors"] == []
    assert "report" in out


def test_dispatch_missing_modules_errors(project):
    root, _ = project
    with pytest.raises(ConciergeError):
        handle_concierge_tool("derive-contract", root)


def test_dispatch_check_returns_drift(project):
    root, src = project
    derived = handle_concierge_tool("derive-contract", root, modules=["models_demo"], pythonpath=src)
    body = derived["contract_text"].split("\n", 2)[2]   # strip 2 provenance lines
    drift = handle_concierge_tool("derive-contract", root, modules=["models_demo"], pythonpath=src,
                                  check=True, live_schema_text=body)
    assert drift["verdict"] == "in_sync" and drift["drift"] == []


# ── CLI ───────────────────────────────────────────────────────────────────────

def _cli(root, src, *extra):
    return runner.invoke(concierge_app, ["derive-contract", str(root),
                                         "--models", "models_demo", "--pythonpath", src, *extra])


def test_cli_preview_writes_nothing(project):
    root, src = project
    res = _cli(root, src)
    assert res.exit_code == 0 and "preview only" in res.stdout
    assert not (root / "prisma" / "schema.prisma").exists()


def test_cli_apply_writes_candidate(project):
    root, src = project
    res = _cli(root, src, "--apply", "--out", "schema.prisma")
    assert res.exit_code == 0
    contract = root / "schema.prisma"
    assert contract.is_file() and "unratified" in contract.read_text()


def test_cli_apply_no_clobber_without_force(project):
    root, src = project
    _cli(root, src, "--apply", "--out", "schema.prisma")
    res2 = _cli(root, src, "--apply", "--out", "schema.prisma")
    assert "skipped" in res2.stdout and "wrote" not in res2.stdout


def test_cli_check_in_sync_then_drift(project):
    root, src = project
    _cli(root, src, "--apply", "--out", "schema.prisma")
    ok = _cli(root, src, "--check", "--out", "schema.prisma")
    assert ok.exit_code == 0 and "in_sync" in ok.stdout
    (root / "schema.prisma").write_text(
        (root / "schema.prisma").read_text() + "\nmodel Ghost { id String @id }\n", encoding="utf-8")
    drifted = _cli(root, src, "--check", "--out", "schema.prisma")
    assert drifted.exit_code == 1 and "drift" in drifted.stdout.lower()


# ── MCP conformance ───────────────────────────────────────────────────────────

def test_derive_in_both_mcp_enums():
    base = Path(__file__).resolve().parents[4] / "mcp" / "startd8-mcp-builder"
    for f in ("startd8_mcp.py", "startd8_mcp_server/server.py"):
        assert 'DERIVE_CONTRACT = "derive-contract"' in (base / f).read_text(encoding="utf-8")


def test_mcp_path_writes_nothing_for_derive(project):
    """The MCP-reachable path (handle_concierge_tool) writes nothing for derive-contract."""
    root, src = project
    snap = lambda: sorted(str(p.relative_to(root)) for p in root.rglob("*")
                          if "__pycache__" not in p.parts)  # ignore interpreter bytecode
    before = snap()
    handle_concierge_tool("derive-contract", root, modules=["models_demo"], pythonpath=src)
    assert snap() == before
