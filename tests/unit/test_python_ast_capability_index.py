"""Unit tests for Python AST capability index generator."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
GEN = _REPO / "scripts" / "gen_python_ast_capability_index.py"
OUT = _REPO / "docs" / "design" / "python-capability-index"


@pytest.mark.unit
def test_generator_check_passes() -> None:
    proc = subprocess.run(
        [sys.executable, str(GEN), "--check"],
        cwd=_REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


@pytest.mark.unit
def test_ast_nodes_numbered_contiguously() -> None:
    nodes = json.loads((OUT / "ast-nodes.json").read_text())["nodes"]
    ids = [n["id"] for n in nodes]
    assert ids[0] == "PY-AST-001"
    assert len(ids) == len(set(ids))
    assert len(nodes) >= 100


@pytest.mark.unit
def test_crosswalk_covers_landscape_section5() -> None:
    patterns = json.loads((OUT / "communication-crosswalk.json").read_text())["patterns"]
    ids = {p["id"] for p in patterns}
    assert "PY-OTEL-5.1-HTTP" in ids
    assert "PY-OTEL-5.3-RPC" in ids
    assert "PY-OTEL-5.4-MESSAGING" in ids
    assert "PY-OTEL-5.5-DATABASE" in ids
    assert "PY-OTEL-5.6-FEATURE-FLAGS" in ids


@pytest.mark.unit
def test_manifest_kinds_include_async() -> None:
    kinds = json.loads((OUT / "manifest-kinds.json").read_text())["kinds"]
    kind_names = {k["kind"] for k in kinds}
    assert "async_function" in kind_names
    assert "class" in kind_names
