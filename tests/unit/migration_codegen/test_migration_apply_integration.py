"""Gold-standard proof: a generated baseline revision actually APPLIES with real Alembic.

Renders a real project (backend tables + the completed scaffold harness), writes a baseline revision
from the contract, runs `alembic upgrade head` for real, and asserts the table landed in SQLite. Needs
alembic (a generated-app dev dep, not an SDK dep) → skips where it's absent, like the fastapi runtime
smoke test.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys

import pytest

pytest.importorskip("alembic")

from startd8.backend_codegen import render_backend          # noqa: E402
from startd8.migration_codegen import next_revision          # noqa: E402
from startd8.scaffold_codegen import render_scaffold          # noqa: E402

SCHEMA = (
    "model Job {\n"
    "  id String @id @default(cuid())\n"
    '  ownerId String @default("local")\n'
    "  title String\n"
    '  status String @default("active")\n'
    "}\n"
)


def test_generated_baseline_applies_with_alembic(tmp_path):
    # 1. a real project tree: backend (app/tables.py + db.py + …) + scaffold (alembic harness).
    for rel, content in render_backend(SCHEMA, manifest_text="", human_inputs_text=""):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    for rel, content in render_scaffold(""):                 # defaults: package=app, migrations on
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    # 2. write the baseline revision (FR-MG-2) into the completed versions/ dir (FR-MG-1).
    versions = tmp_path / "alembic" / "versions"
    fname, text, plan = next_revision(versions, SCHEMA, "baseline")
    assert plan.is_baseline
    (versions / fname).write_text(text, encoding="utf-8")

    # 3. apply it for real — `alembic upgrade head`.
    db = tmp_path / "app.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "PYTHONPATH": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=tmp_path, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # 4. the table — and its server-default'd column — actually exist in the DB.
    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "job" in tables
        cols = {r[1] for r in con.execute("PRAGMA table_info(job)")}
        assert {"id", "ownerId", "title", "status"} <= cols
    finally:
        con.close()
