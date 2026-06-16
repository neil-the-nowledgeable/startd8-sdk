"""Deployment-mode capability — settings.py spine (DEPLOYMENT_MODE_REQUIREMENTS.md v0.3, Plan A2/A9).

Proves the load-bearing FR-CFG-7a property: the single mode-varying file (`app/settings.py`)
self-describes its baked mode in the header, so the **schema-only prime-contractor skip-hook**
(`owned_file_in_sync` / `PydanticSQLModelProvider.is_in_sync`) re-derives and verifies it with **no
`app.yaml`** read. Also locks the R4 regression (installed == today: no settings.py) and idempotency.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen import (
    embedded_mode,
    owned_file_in_sync,
    render_backend,
    render_settings,
)
from startd8.backend_codegen.crud_generator import CANONICAL_LAYOUT
from startd8.backend_codegen.drift import check_drift, embedded_artifact_kind
from startd8.backend_codegen.provider import PydanticSQLModelProvider
from startd8.contractors.deterministic_providers import ProviderContext

pytestmark = pytest.mark.unit

SCHEMA = """\
model Profile {
  id   String @id
  name String
}
"""

SETTINGS_PATH = "app/settings.py"


# --- R4 regression: installed == today (settings.py is deployed-only, D11) -----------------------

def test_installed_emits_no_settings_and_equals_default():
    installed = dict(render_backend(SCHEMA, deployment_mode="installed"))
    default = dict(render_backend(SCHEMA))  # default is installed
    assert SETTINGS_PATH not in installed
    assert installed == default  # byte-identical to today — no regression


def test_deployed_adds_settings_and_auth_seam():
    installed = dict(render_backend(SCHEMA, deployment_mode="installed"))
    deployed = dict(render_backend(SCHEMA, deployment_mode="deployed"))
    # Deployed adds two deployed-only files: settings.py (mode-varying) + auth.py (reference seam, M2).
    assert set(deployed) - set(installed) == {SETTINGS_PATH, "app/auth.py"}
    assert set(installed) - set(deployed) == set()
    # Every SHARED file is byte-identical across modes (the mode lives only in settings.py).
    for path in installed:
        assert installed[path] == deployed[path], f"{path} differs by mode but must not"


# --- settings.py shape: self-describes mode, valid Python ----------------------------------------

def test_settings_self_describes_mode_and_compiles():
    text = render_settings(SCHEMA, mode="deployed")
    assert embedded_artifact_kind(text) == "python-settings"
    assert embedded_mode(text) == "deployed"
    assert '# startd8-mode: deployed' in text
    assert 'DEPLOYMENT_MODE = "deployed"' in text
    compile(text, "app/settings.py", "exec")  # must be valid Python


def test_installed_and_deployed_settings_differ_by_exactly_two_lines():
    a = render_settings(SCHEMA, mode="installed").splitlines()
    b = render_settings(SCHEMA, mode="deployed").splitlines()
    assert len(a) == len(b)
    diffs = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    # Only the header `# startd8-mode:` line and the `DEPLOYMENT_MODE = "…"` assignment differ.
    assert len(diffs) == 2, [(a[i], b[i]) for i in diffs]


def test_render_settings_rejects_invalid_mode():
    with pytest.raises(ValueError, match="mode must be one of"):
        render_settings(SCHEMA, mode="hybrid")


# --- Idempotency per mode (FR-DET-2) -------------------------------------------------------------

def test_settings_is_byte_identical_per_mode():
    assert render_settings(SCHEMA, mode="deployed") == render_settings(SCHEMA, mode="deployed")
    assert dict(render_backend(SCHEMA, deployment_mode="deployed")) == dict(
        render_backend(SCHEMA, deployment_mode="deployed")
    )


# --- FR-CFG-7a: skip-hook re-derives the baked mode WITHOUT app.yaml (THE critical property) ------

def test_skip_hook_verifies_settings_with_only_schema():
    text = render_settings(SCHEMA, mode="deployed")
    # owned_file_in_sync takes ONLY schema_text — no app.yaml, no manifest. This is the $0.00 path.
    assert owned_file_in_sync(SCHEMA, text) is True


def test_provider_is_in_sync_with_no_app_yaml(tmp_path):
    # A realistic skip-hook context: the .prisma schema resolves, but NO app.yaml exists on disk.
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA, encoding="utf-8")
    text = render_settings(SCHEMA, mode="deployed")
    p = tmp_path / SETTINGS_PATH
    ctx = ProviderContext(project_root=tmp_path, source_anchors=("prisma/schema.prisma",))
    prov = PydanticSQLModelProvider()
    assert prov.owns(p, text) is True
    assert prov.is_in_sync(p, text, ctx) is True  # re-derived mode from the file's own header
    assert not (tmp_path / "app.yaml").exists()  # proven: no app.yaml was needed


# --- Drift detection: schema change is stale; mode tamper is tampered -----------------------------

def test_schema_change_is_stale():
    text = render_settings(SCHEMA, mode="deployed")
    changed = SCHEMA + "\nmodel Extra {\n  id String @id\n}\n"
    assert owned_file_in_sync(changed, text) is False
    assert check_drift(changed, text, source_file="prisma/schema.prisma").status == "stale"


def test_mode_constant_tamper_is_tampered():
    # Flip only the baked constant, leaving the header mode = deployed → re-render (deployed) won't
    # match the tampered body → tampered. (A *consistent* mode rewrite is a valid file, by design.)
    text = render_settings(SCHEMA, mode="deployed")
    tampered = text.replace('DEPLOYMENT_MODE = "deployed"', 'DEPLOYMENT_MODE = "installed"')
    assert tampered != text
    res = check_drift(SCHEMA, tampered, source_file="prisma/schema.prisma")
    assert res.status == "tampered"
    assert owned_file_in_sync(SCHEMA, tampered) is False


def test_canonical_layout_registers_settings():
    assert CANONICAL_LAYOUT["python-settings"] == SETTINGS_PATH
