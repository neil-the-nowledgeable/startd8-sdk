"""Deployment-mode M1-A — db.py consumes settings, the db↔settings gate, and CLI mode wiring.

Builds on the M0 spine (test_deployment_mode.py): proves db.py tolerantly consumes app/settings.py
(deployed) / falls back to today (installed), stays byte-identical across modes, that the generation-
time db↔settings contract gate (R1-S6) catches a settings rename, the emitted runtime behaviors
(create_all gate FR-PER-3, pooled engine FR-CON-1, directional fail-closed FR-CFG-4), and that
`startd8 generate backend` honors `--mode` / `--app-manifest` (FR-CLI-1).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.backend_codegen import (
    render_backend,
    render_settings,
    verify_db_settings_contract,
)
from startd8.backend_codegen.crud_generator import render_db
from startd8.cli_generate import generate_app

pytestmark = pytest.mark.unit

runner = CliRunner()

SCHEMA = """\
model Profile {
  id   String @id
  name String
}
"""
SETTINGS_PATH = "app/settings.py"
DB_PATH = "app/db.py"


def _exec_settings(mode: str) -> dict:
    ns: dict = {}
    exec(compile(render_settings(SCHEMA, mode=mode), "app/settings.py", "exec"), ns)
    return ns


# --- A3: db.py tolerantly consumes settings, stays mode-invariant --------------------------------

def test_db_tolerantly_imports_and_consumes_settings():
    db = render_db(SCHEMA)
    assert "from . import settings as _settings" in db
    assert "except ModuleNotFoundError:" in db  # installed fallback (no settings.py)
    for call in (
        "_settings.database_url()",
        "_settings.engine_options()",
        "_settings.should_create_all()",
        "_settings.validate_runtime_mode()",
    ):
        assert call in db, call
    # Today's contract still holds (existing tests + behavior): create_all + the two defs survive.
    assert "SQLModel.metadata.create_all(engine)" in db
    assert "def init_db() -> None:" in db
    assert "def get_session() -> Iterator[Session]:" in db
    compile(db, "app/db.py", "exec")  # valid Python


def test_db_is_byte_identical_across_modes():
    installed = dict(render_backend(SCHEMA, deployment_mode="installed"))
    deployed = dict(render_backend(SCHEMA, deployment_mode="deployed"))
    # db.py is mode-invariant: the mode lives only in settings.py (the single mode-varying file).
    assert installed[DB_PATH] == deployed[DB_PATH]
    assert DB_PATH in installed and SETTINGS_PATH not in installed


# --- R1-S6: generation-time db↔settings contract gate (HAYAI) ------------------------------------

def test_db_settings_contract_gate_holds_for_generated_pair():
    db = render_db(SCHEMA)
    settings = render_settings(SCHEMA, mode="deployed")
    assert verify_db_settings_contract(db, settings) == ()


def test_db_settings_contract_gate_catches_a_rename():
    db = render_db(SCHEMA)
    # Simulate a settings refactor that renamed should_create_all -> may_create_all.
    settings = render_settings(SCHEMA, mode="deployed").replace(
        "def should_create_all(", "def may_create_all("
    )
    issues = verify_db_settings_contract(db, settings)
    assert any("should_create_all" in i for i in issues), issues


# --- Emitted runtime behaviors (exec the generated settings.py) -----------------------------------

def test_deployed_settings_runtime_behavior(monkeypatch):
    ns = _exec_settings("deployed")
    assert ns["DEPLOYMENT_MODE"] == "deployed"
    assert ns["should_create_all"]() is False  # FR-PER-3: no auto create_all on a shared DB
    opts = ns["engine_options"]()
    assert opts.get("pool_size") and opts.get("pool_pre_ping") is True  # FR-CON-1 pool
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):  # FR-PER-2: deployed has no local default
        ns["database_url"]()
    monkeypatch.setenv("DATABASE_URL", "postgresql://host/db")
    assert ns["database_url"]() == "postgresql://host/db"


def test_installed_settings_runtime_behavior(monkeypatch):
    ns = _exec_settings("installed")
    assert ns["should_create_all"]() is True  # dev bootstrap allowed
    assert ns["engine_options"]() == {}  # SQLite single-writer defaults
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert ns["database_url"]() == "sqlite:///./app.db"  # local-first default


def test_validate_runtime_mode_is_directional_fail_closed(monkeypatch):
    # FR-CFG-4: installed binary + env says deployed (the downgrade direction) -> refuse to start.
    ns_i = _exec_settings("installed")
    monkeypatch.setenv("STARTD8_DEPLOYMENT_MODE", "deployed")
    with pytest.raises(SystemExit):
        ns_i["validate_runtime_mode"]()
    # Safe direction: deployed binary + env says installed -> warn, do not raise.
    ns_d = _exec_settings("deployed")
    monkeypatch.setenv("STARTD8_DEPLOYMENT_MODE", "installed")
    ns_d["validate_runtime_mode"]()  # no exception
    # Matching/absent -> OK.
    monkeypatch.delenv("STARTD8_DEPLOYMENT_MODE", raising=False)
    ns_d["validate_runtime_mode"]()


# --- FR-CLI-1: `generate backend` honors --mode / --app-manifest ---------------------------------

def _write_schema(tmp_path):
    p = tmp_path / "schema.prisma"
    p.write_text(SCHEMA, encoding="utf-8")
    return p


def test_cli_mode_deployed_emits_settings(tmp_path):
    schema = _write_schema(tmp_path)
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--mode", "deployed"],
    )
    assert res.exit_code == 0, res.output
    assert (tmp_path / SETTINGS_PATH).exists()
    assert "# startd8-mode: deployed" in (tmp_path / SETTINGS_PATH).read_text()


def test_cli_default_mode_installed_no_settings(tmp_path):
    schema = _write_schema(tmp_path)
    res = runner.invoke(
        generate_app, ["backend", "--schema", str(schema), "--out", str(tmp_path)]
    )
    assert res.exit_code == 0, res.output
    assert not (tmp_path / SETTINGS_PATH).exists()  # installed == today


def test_cli_app_manifest_drives_mode(tmp_path):
    schema = _write_schema(tmp_path)
    manifest = tmp_path / "app.yaml"
    # A coherent deployed manifest (shared DSN) — the FR-CFG-5 guard rejects deployed+SQLite.
    manifest.write_text(
        "deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n",
        encoding="utf-8",
    )
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path),
         "--app-manifest", str(manifest)],
    )
    assert res.exit_code == 0, res.output
    assert (tmp_path / SETTINGS_PATH).exists()


def test_cli_explicit_mode_overrides_manifest(tmp_path):
    schema = _write_schema(tmp_path)
    manifest = tmp_path / "app.yaml"
    manifest.write_text("deployment:\n  mode: deployed\n", encoding="utf-8")
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path),
         "--app-manifest", str(manifest), "--mode", "installed"],
    )
    assert res.exit_code == 0, res.output
    assert not (tmp_path / SETTINGS_PATH).exists()  # --mode installed wins


def test_cli_invalid_mode_fails_loud(tmp_path):
    schema = _write_schema(tmp_path)
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--mode", "hybrid"],
    )
    assert res.exit_code != 0


# --- R1-S4: checked-in golden trees, byte-pinned in CI -------------------------------------------

_FIXTURES = Path(__file__).parent / "fixtures" / "deployment_mode"


@pytest.mark.parametrize("mode", ["installed", "deployed"])
def test_golden_tree_byte_identity(mode):
    """Regenerate the full tree and assert it matches the committed {path: sha256} golden (R1-S4).

    The keystone regression guard: `installed` must stay the frozen golden and `deployed` must differ
    only by app/settings.py. If a legitimate generator change moves these, regenerate the fixtures and
    review the diff consciously.
    """
    tree = render_backend(SCHEMA, deployment_mode=mode)
    actual = {rel: hashlib.sha256(text.encode()).hexdigest() for rel, text in tree}
    golden = json.loads((_FIXTURES / f"{mode}.sha256.json").read_text())
    added = sorted(set(actual) - set(golden))
    removed = sorted(set(golden) - set(actual))
    changed = sorted(k for k in golden if k in actual and golden[k] != actual[k])
    assert actual == golden, f"{mode} tree drifted: added={added} removed={removed} changed={changed}"


def test_golden_deployed_delta_is_exactly_settings():
    installed = json.loads((_FIXTURES / "installed.sha256.json").read_text())
    deployed = json.loads((_FIXTURES / "deployed.sha256.json").read_text())
    assert set(deployed) - set(installed) == {SETTINGS_PATH}
    assert [k for k in installed if installed[k] != deployed.get(k)] == []  # shared files identical
