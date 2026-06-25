"""FR-DC-14 containment tests for derive-contract introspection.

Each maps to a security invariant: subprocess round-trip, **scrubbed env** (host secrets do not
cross), and **fail-closed** on import error / timeout / partial import (never a partial result).
The target modules are written to a tmp dir and imported by the real subprocess.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from startd8.concierge.derive import DeriveImportError, run_contained_introspection
from startd8.concierge.derive.introspect import KIND_LIST_MODEL, KIND_SCALAR


def _write_module(tmp_path: Path, name: str, body: str) -> str:
    (tmp_path / f"{name}.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return name


def test_subprocess_roundtrip_matches_logic(tmp_path):
    mod = _write_module(tmp_path, "models_ok", """
        from typing import List
        from pydantic import BaseModel
        class Child(BaseModel):
            id: str
            name: str
        class Parent(BaseModel):
            id: str
            children: List[Child] = []
    """)
    r = run_contained_introspection([mod], project_pythonpath=str(tmp_path))
    ents = {e.name: e for e in r.entities}
    assert set(ents) == {"Parent", "Child"}
    fmap = {f.name: f for f in ents["Parent"].fields}
    assert fmap["id"].kind == KIND_SCALAR
    assert fmap["children"].kind == KIND_LIST_MODEL and fmap["children"].ref_model == "Child"
    assert mod in r.imported_modules


def test_scrubbed_env_does_not_leak_host_secret(tmp_path, monkeypatch):
    """A secret in the parent env must NOT be visible to the introspection subprocess."""
    monkeypatch.setenv("LEAKED_SECRET", "topsecret-do-not-cross")
    out = tmp_path / "leak_probe.txt"
    mod = _write_module(tmp_path, "models_probe", f"""
        import os
        from pathlib import Path
        from pydantic import BaseModel
        Path(r"{out}").write_text(os.environ.get("LEAKED_SECRET", "absent"))
        class M(BaseModel):
            id: str
    """)
    run_contained_introspection([mod], project_pythonpath=str(tmp_path))
    assert out.read_text() == "absent"   # the subprocess saw no host secret


def test_fail_closed_on_import_error(tmp_path):
    mod = _write_module(tmp_path, "models_boom", """
        raise RuntimeError("top-level import blew up")
        from pydantic import BaseModel
        class M(BaseModel):
            id: str
    """)
    with pytest.raises(DeriveImportError):
        run_contained_introspection([mod], project_pythonpath=str(tmp_path))


def test_fail_closed_on_partial_import(tmp_path):
    """One bad module in the set aborts the whole run — no partial contract (R1-S2)."""
    good = _write_module(tmp_path, "models_good", """
        from pydantic import BaseModel
        class Good(BaseModel):
            id: str
    """)
    bad = _write_module(tmp_path, "models_bad", """
        import nonexistent_dependency_xyz  # ImportError at import time
    """)
    with pytest.raises(DeriveImportError):
        run_contained_introspection([good, bad], project_pythonpath=str(tmp_path))


def test_fail_closed_on_timeout(tmp_path):
    mod = _write_module(tmp_path, "models_slow", """
        import time
        from pydantic import BaseModel
        time.sleep(3)
        class M(BaseModel):
            id: str
    """)
    with pytest.raises(DeriveImportError):
        run_contained_introspection([mod], project_pythonpath=str(tmp_path), timeout=1.0)


def test_navig8_via_subprocess(tmp_path):
    """The real oracle, through the contained path (skips if startd8_work isn't importable)."""
    work_src = "/Users/neilyashinsky/Documents/dev/startd8-work/src"
    if not Path(work_src, "startd8_work", "legal", "tree_models.py").is_file():
        pytest.skip("startd8_work not present")
    r = run_contained_introspection(
        ["startd8_work.legal.tree_models"],
        project_pythonpath=work_src,
        model_names=["DecisionTree", "TreeNode", "Perspective"],
    )
    ents = {e.name: e for e in r.entities}
    assert ents["TreeNode"].has_explicit_id is True
    assert ents["DecisionTree"].has_explicit_id is False
