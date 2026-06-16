"""Manifest-driven scaffold generator (class-2 determinism) — REQ-SCAF.

Proves the plumbing emitter is byte-stable, drift-checked against app.yaml, produces a valid
pyproject (the #1 rebuild blocker) and compilable Python, and that the provider recognizes/verifies
its files generically. Non-overlapping with backend_codegen.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from startd8.scaffold_codegen import (
    ScaffoldFileProvider,
    parse_app_manifest,
    render_scaffold,
    scaffold_in_sync,
)
from startd8.contractors.deterministic_providers import ProviderContext

pytestmark = pytest.mark.unit

MANIFEST = """
app:
  name: startdate
  package: app
persistence:
  path: ./data/startd8.db
logging:
  file: ./data/logs/startd8.log
migrations:
  enabled: true
container:
  dockerfile: true
""".strip()


def test_defaults_when_absent():
    m = parse_app_manifest(None)
    assert m.name == "app" and m.package == "app" and m.migrations and m.dockerfile


def test_unknown_key_fails_loud():
    with pytest.raises(ValueError):
        parse_app_manifest("nonsense_key: 1")


# --- Deployment mode (DEPLOYMENT_MODE_REQUIREMENTS.md FR-CFG-1/2, Plan Step A1) -------------------

def test_deployment_mode_defaults_to_installed():
    # FR-CFG-1: absent `deployment:` block reproduces today's behavior (installed default).
    assert parse_app_manifest(None).deployment_mode == "installed"
    assert parse_app_manifest(MANIFEST).deployment_mode == "installed"


def test_deployment_mode_deployed_parses():
    m = parse_app_manifest("deployment:\n  mode: deployed\n")
    assert m.deployment_mode == "deployed"


def test_deployment_mode_invalid_value_fails_loud():
    # Strict enum (NR-2): exactly two modes; anything else fails loud, never coerced.
    with pytest.raises(ValueError, match="deployment.mode"):
        parse_app_manifest("deployment:\n  mode: hybrid\n")


def test_deployment_unknown_subkey_fails_loud():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_app_manifest("deployment:\n  mode: deployed\n  bogus: 1\n")


def test_deployment_block_must_be_a_mapping():
    with pytest.raises(ValueError, match="`deployment` must be a mapping"):
        parse_app_manifest("deployment: 5\n")


# --- Tier B: deployment.tenant declaration (M3 / FR-TEN-2) ---------------------------------------

def test_tenant_absent_by_default():
    m = parse_app_manifest("deployment:\n  mode: deployed\n")
    assert m.tenant_model is None and m.tenant_owner_field is None and m.has_tenant is False


def test_tenant_parses():
    m = parse_app_manifest(
        "deployment:\n  mode: deployed\n  tenant:\n    model: User\n    owner_field: owner_id\n"
    )
    assert m.tenant_model == "User" and m.tenant_owner_field == "owner_id" and m.has_tenant is True


def test_tenant_must_be_a_mapping():
    with pytest.raises(ValueError, match="`deployment.tenant` must be a mapping"):
        parse_app_manifest("deployment:\n  mode: deployed\n  tenant: User\n")


def test_tenant_requires_model_and_owner_field():
    with pytest.raises(ValueError, match="owner_field"):
        parse_app_manifest("deployment:\n  mode: deployed\n  tenant:\n    model: User\n")
    with pytest.raises(ValueError, match="model"):
        parse_app_manifest("deployment:\n  mode: deployed\n  tenant:\n    owner_field: owner_id\n")


def test_tenant_unknown_subkey_fails_loud():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_app_manifest(
            "deployment:\n  mode: deployed\n  tenant:\n    model: User\n    owner_field: o\n    x: 1\n"
        )


def test_render_is_byte_identical_and_full_set():
    a = render_scaffold(MANIFEST)
    assert a == render_scaffold(MANIFEST)
    paths = {rel for rel, _ in a}
    assert paths == {
        "pyproject.toml",
        "app/logging_config.py",
        ".env.example",
        "run.sh",                          # FR-NET-1/2: local run, bind mode-derived
        "Dockerfile",
        "alembic.ini",
        "alembic/env.py",
        "alembic/script.py.mako",          # FR-MG-1: the revision template
        "alembic/versions/.gitkeep",       # FR-MG-1: the versions dir must exist
    }
    for rel, content in a:
        if rel.endswith(".gitkeep"):
            continue  # intentional empty placeholder — no header
        assert "# startd8-artifact: scaffold-" in content
        assert "# manifest-sha256:" in content


def test_env_example_is_byte_identical_and_carries_db_url():
    files = dict(render_scaffold(MANIFEST))
    assert ".env.example" in files
    env = files[".env.example"]
    assert env == dict(render_scaffold(MANIFEST))[".env.example"]  # byte-identical
    assert "# startd8-artifact: scaffold-env" in env
    assert "ANTHROPIC_API_KEY=" in env
    assert "DATABASE_URL=sqlite:///./data/startd8.db" in env  # db_path from the manifest
    assert "COST_BUDGET_USD=10" in env
    assert scaffold_in_sync(MANIFEST, env) is True
    assert scaffold_in_sync(MANIFEST, env.replace("10", "99", 1)) is False  # tampered


def test_pyproject_parses_and_has_deps():
    files = dict(render_scaffold(MANIFEST))
    data = tomllib.loads(files["pyproject.toml"])  # tomllib ignores the leading # header lines
    assert data["project"]["name"] == "startdate"
    assert "fastapi" in data["project"]["dependencies"]
    assert "alembic" in data["project"]["optional-dependencies"]["dev"]


def test_drift_in_sync_and_tamper():
    files = dict(render_scaffold(MANIFEST))
    py = files["app/logging_config.py"]
    assert scaffold_in_sync(MANIFEST, py) is True
    assert scaffold_in_sync(MANIFEST, py.replace("INFO", "DEBUG", 1)) is False  # tampered
    assert scaffold_in_sync("app:\n  name: other", py) is False  # stale (manifest changed)


def test_provider_owns_and_verifies(tmp_path):
    files = dict(render_scaffold(MANIFEST))
    (tmp_path / "app.yaml").write_text(MANIFEST, encoding="utf-8")
    ctx = ProviderContext(project_root=tmp_path, source_anchors=("app.yaml",))
    prov = ScaffoldFileProvider()
    py = files["app/logging_config.py"]
    assert prov.owns(tmp_path / "app/logging_config.py", py) is True
    assert prov.is_in_sync(tmp_path / "app/logging_config.py", py, ctx) is True
    assert prov.owns(tmp_path / "x.py", "print('hi')") is False


def test_generated_python_compiles(tmp_path):
    for rel, content in render_scaffold(MANIFEST):
        if not rel.endswith(".py"):
            continue
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_extra_dependencies_flow_to_pyproject_and_owned_requirements():
    """G4: app.yaml `extra_dependencies` flow into pyproject `dependencies` + requirements-owned.txt
    so an owned-glue capability's runtime deps reach a deploy without a hand-maintained file."""
    m = MANIFEST + "\nextra_dependencies:\n  - reportlab\n  - pypdf\n"
    files = dict(render_scaffold(m))
    py = files["pyproject.toml"]
    assert "reportlab" in py and "pypdf" in py                 # in [project].dependencies
    owned = files["requirements-owned.txt"]
    assert owned.splitlines()[-2:] == ["reportlab", "pypdf"]   # generated deploy file
    assert scaffold_in_sync(m, owned) is True                  # owned + drift-tracked
    # no extra_dependencies → no requirements-owned.txt (FR: emitted only when declared)
    assert "requirements-owned.txt" not in dict(render_scaffold(MANIFEST))


def test_extra_dependencies_must_be_a_string_list():
    import pytest as _pytest
    with _pytest.raises(ValueError, match="extra_dependencies"):
        render_scaffold(MANIFEST + "\nextra_dependencies:\n  reportlab: yes\n")


def test_scaffold_check_is_clean_after_generate_gitkeep_not_flagged(tmp_path):
    """`generate scaffold --check` reaches in_sync right after a clean generate — the headerless
    alembic/versions/.gitkeep placeholder must NOT perma-flag the drift gate."""
    from typer.testing import CliRunner
    from startd8.cli_generate import generate_app

    runner = CliRunner()
    man = tmp_path / "app.yaml"
    man.write_text(MANIFEST, encoding="utf-8")
    proj = tmp_path / "proj"
    assert runner.invoke(generate_app, ["scaffold", "--manifest", str(man), "--out", str(proj)]).exit_code == 0
    (proj / "alembic" / "versions" / ".gitkeep").write_text("", encoding="utf-8")  # ensure it exists
    chk = runner.invoke(generate_app, ["scaffold", "--manifest", str(man), "--out", str(proj), "--check"])
    assert chk.exit_code == 0, chk.output            # in_sync — no .gitkeep drift
    assert ".gitkeep" not in chk.output


def test_alembic_mako_completes_the_migration_harness():
    """FR-MG-1: the scaffold emits script.py.mako (so `alembic revision` works) + a versions dir."""
    files = dict(render_scaffold(MANIFEST))
    mako = files["alembic/script.py.mako"]
    # the canonical revision-template substitution points alembic fills in
    for tok in ("${message}", "${up_revision}", "${repr(down_revision)}",
                "def upgrade()", "def downgrade()", "from alembic import op"):
        assert tok in mako, tok
    assert files["alembic/versions/.gitkeep"] == ""              # empty dir placeholder
    # env.py uses SQLite batch mode (needed to ALTER) — FR-MG-1
    assert "render_as_batch=True" in files["alembic/env.py"]
    # the mako is owned + drift-tracked like the other scaffold files
    assert scaffold_in_sync(MANIFEST, mako) is True
    assert scaffold_in_sync(MANIFEST, mako.replace("upgrade", "upgradeX", 1)) is False
