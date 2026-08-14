"""M2/A6 — the deployed-mode reference auth seam (app/auth.py, FR-IDN-2/3/4 + AUTH_SEAM_JWT).

Proves: deployed emits app/auth.py (installed does not); it carries the machine-detectable
REFERENCE_AUTH_SEAM marker (R1-F4) + the get_principal/require_principal mechanism + the
authenticated-but-not-tenant-isolated banner (FR-IDN-4); Bearer/JWT decode-only ingress (no
spoofable X-Principal-Id); it is skip-hook drift-verifiable like any standard schema-only
artifact; and the dormant FR-CFG-5 `deployed-auth-no-tenant` WARN now fires.
"""

from __future__ import annotations

import ast
import base64
import json
import time

import pytest
from typer.testing import CliRunner

from startd8.backend_codegen import (
    is_reference_auth_seam,
    is_verified_auth_seam,
    owned_file_in_sync,
    render_auth_seam,
    render_backend,
)
from startd8.backend_codegen.drift import check_drift, embedded_artifact_kind
from startd8.cli_generate import generate_app
from startd8.scaffold_codegen import parse_app_manifest
from startd8.scaffold_codegen.coherence import evaluate_coherence

pytestmark = pytest.mark.unit

runner = CliRunner()

SCHEMA = "model Profile {\n  id   String @id\n  name String\n}\n"
AUTH_PATH = "app/auth.py"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unsigned_jwt(claims: dict) -> str:
    header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps(claims).encode())
    return f"{header}.{payload}.sig"


def test_auth_seam_content_and_marker():
    text = render_auth_seam(SCHEMA)
    assert embedded_artifact_kind(text) == "python-auth-seam"
    assert "REFERENCE_AUTH_SEAM = True" in text  # machine-detectable marker (R1-F4)
    assert is_reference_auth_seam(text) is True
    assert "def get_principal(" in text and "def require_principal(" in text
    assert "AUTHENTICATED BUT NOT TENANT-ISOLATED" in text  # FR-IDN-4 banner
    compile(text, AUTH_PATH, "exec")  # valid Python (imports not executed)
    ast.parse(text)


def test_is_reference_auth_seam_false_when_replaced():
    replaced = render_auth_seam(SCHEMA).replace("REFERENCE_AUTH_SEAM = True", "REFERENCE_AUTH_SEAM = False")
    assert is_reference_auth_seam(replaced) is False


def test_deployed_emits_auth_installed_does_not():
    installed = dict(render_backend(SCHEMA, deployment_mode="installed"))
    deployed = dict(render_backend(SCHEMA, deployment_mode="deployed"))
    assert AUTH_PATH not in installed
    assert AUTH_PATH in deployed


def test_auth_seam_skip_hook_verifies_with_schema_only():
    text = render_auth_seam(SCHEMA)
    assert owned_file_in_sync(SCHEMA, text) is True  # standard schema-only $0.00 skip path


def test_auth_seam_drift_schema_change_and_tamper():
    text = render_auth_seam(SCHEMA)
    changed = SCHEMA + "\nmodel Extra {\n  id String @id\n}\n"
    assert check_drift(changed, text).status == "stale"
    tampered = text.replace("authentication required", "nope")
    assert check_drift(SCHEMA, tampered).status == "tampered"


def test_coherence_warns_authenticated_not_isolated():
    # M2: deployed emits auth but tenancy is not declared -> the dormant WARN now fires.
    manifest = parse_app_manifest(
        "deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n"
    )
    findings = evaluate_coherence(manifest, has_auth_seam=True)
    codes = {f.code: f.severity for f in findings}
    assert codes.get("deployed-auth-no-tenant") == "WARN"


def test_cli_deployed_build_emits_auth_and_warns(tmp_path):
    schema = tmp_path / "schema.prisma"
    schema.write_text(SCHEMA, encoding="utf-8")
    manifest = tmp_path / "app.yaml"
    manifest.write_text(
        "deployment:\n  mode: deployed\npersistence:\n  path: postgresql://db/app\n"
        "deploy:\n  trust_gateway: true\n",  # ack gateway → isolates the auth-no-tenant WARN path
        encoding="utf-8",
    )
    res = runner.invoke(
        generate_app,
        ["backend", "--schema", str(schema), "--out", str(tmp_path), "--app-manifest", str(manifest)],
    )
    assert res.exit_code == 0, res.output  # WARN, not ERROR
    assert (tmp_path / AUTH_PATH).exists()
    assert "deployed-auth-no-tenant" in res.output
    auth = (tmp_path / AUTH_PATH).read_text(encoding="utf-8")
    assert "Authorization" in auth and "Bearer" in auth
    assert 'alias="X-Principal-Id"' not in auth


# --- AUTH_SEAM_JWT (Tier 1.1) additive -------------------------------------------------


def test_jwt_bearer_ingress_no_spoofable_header():
    text = render_auth_seam(SCHEMA)
    assert 'alias="Authorization"' in text
    assert "Bearer" in text
    assert 'alias="X-Principal-Id"' not in text
    assert "DECODE-ONLY" in text
    assert "VERIFIED_UPSTREAM = False" in text
    assert is_verified_auth_seam(text) is False

def test_is_verified_auth_seam_true_when_hardened():
    hardened = render_auth_seam(SCHEMA).replace(
        "VERIFIED_UPSTREAM = False", "VERIFIED_UPSTREAM = True"
    )
    assert is_verified_auth_seam(hardened) is True


def test_auth_seam_deterministic():
    assert render_auth_seam(SCHEMA) == render_auth_seam(SCHEMA)


def test_decode_jwt_claims_and_get_principal_runtime():
    """Execute emitted helpers: sub→id, scopes, malformed→None, expired→None."""
    ns: dict = {}
    exec(compile(render_auth_seam(SCHEMA), AUTH_PATH, "exec"), ns)
    decode = ns["_decode_jwt_claims"]
    get_principal = ns["get_principal"]

    good = _unsigned_jwt(
        {
            "sub": "user-1",
            "iss": "https://idp.example",
            "aud": "api",
            "exp": int(time.time()) + 3600,
            "scope": "read write",
            "roles": ["admin"],
        }
    )
    claims = decode(good)
    assert claims["sub"] == "user-1"
    assert decode("not-a-jwt") == {}
    assert decode("a.b") == {}

    principal = get_principal(authorization=f"Bearer {good}")
    assert principal is not None
    assert principal.id == "user-1"
    assert principal.iss == "https://idp.example"
    assert "read" in principal.scopes and "write" in principal.scopes
    assert "admin" in principal.scopes

    assert get_principal(authorization=None) is None
    assert get_principal(authorization="Basic x") is None
    assert get_principal(authorization="Bearer not-a-jwt") is None

    expired = _unsigned_jwt({"sub": "user-1", "exp": int(time.time()) - 10})
    assert get_principal(authorization=f"Bearer {expired}") is None

    no_exp = _unsigned_jwt({"sub": "user-1"})
    assert get_principal(authorization=f"Bearer {no_exp}") is None

    no_sub = _unsigned_jwt({"exp": int(time.time()) + 60})
    assert get_principal(authorization=f"Bearer {no_sub}") is None


def test_require_principal_401_on_expired():
    ns: dict = {}
    exec(compile(render_auth_seam(SCHEMA), AUTH_PATH, "exec"), ns)
    get_principal = ns["get_principal"]
    require_principal = ns["require_principal"]
    from fastapi import HTTPException

    expired = _unsigned_jwt({"sub": "user-1", "exp": int(time.time()) - 5})
    principal = get_principal(authorization=f"Bearer {expired}")
    with pytest.raises(HTTPException) as ei:
        require_principal(principal)
    assert ei.value.status_code == 401
