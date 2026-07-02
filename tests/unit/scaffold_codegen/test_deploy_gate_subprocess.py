"""FR-CDA-5: the deploy-coherence gate subprocess boundary (the substance the MCP tool delegates to).

The FastMCP wrapper is thin glue over ``run_deploy_gate_subprocess``; testing the helper covers the
argv contract, returncode→verdict mapping, fail-closed degradation, and secret-value redaction
without needing the mcp.server package.
"""

from __future__ import annotations

import json

import pytest

from startd8.scaffold_codegen.deploy_readiness import run_deploy_gate_subprocess

pytestmark = pytest.mark.unit

_COHERENT_DEPLOYED = (
    "app:\n  name: demo\n"
    "deployment:\n  mode: deployed\n"
    "persistence:\n  path: postgresql://db/app\n"
    "deploy:\n  trust_gateway: true\n"
)


def test_gate_skip_when_no_app_yaml(tmp_path):
    payload = run_deploy_gate_subprocess(tmp_path)
    assert payload["verdict"] == "skip"  # exit 2 mapped


def test_gate_ok_or_soft_on_coherent_deployed(tmp_path):
    (tmp_path / "app.yaml").write_text(_COHERENT_DEPLOYED, encoding="utf-8")
    payload = run_deploy_gate_subprocess(tmp_path)
    assert payload["verdict"] in ("ok", "soft")
    assert payload["mode"] == "deployed"


def test_gate_hard_on_malformed_app_yaml(tmp_path):
    (tmp_path / "app.yaml").write_text("app: [broken: yaml\n", encoding="utf-8")
    payload = run_deploy_gate_subprocess(tmp_path)
    assert payload["verdict"] == "hard"  # fail-closed, not a crash


def test_gate_fail_closed_when_script_missing(tmp_path):
    payload = run_deploy_gate_subprocess(tmp_path, script_path=tmp_path / "does-not-exist.py")
    assert payload["verdict"] == "hard"
    assert "not found" in payload["reason"]


def test_gate_never_leaks_secret_values(tmp_path):
    (tmp_path / "app.yaml").write_text(_COHERENT_DEPLOYED, encoding="utf-8")
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "infra-contract.yaml").write_text(
        "bindings:\n  - {name: db_password, status: bound, value: SUPER_SECRET_XYZ}\n",
        encoding="utf-8")
    blob = json.dumps(run_deploy_gate_subprocess(tmp_path))
    assert "SUPER_SECRET_XYZ" not in blob


# --- resolve_deployment_readiness: the single readiness+staleness derivation (review-fix) ----------

def _manifest(app_yaml: str):
    from startd8.scaffold_codegen.manifest import parse_app_manifest
    return parse_app_manifest(app_yaml)


def test_resolve_readiness_generated_and_stale(tmp_path):
    from startd8.scaffold_codegen.deploy_readiness import resolve_deployment_readiness
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "infra-contract.yaml").write_text(
        "environments:\n  prod: {}\nbindings:\n  - {name: db, status: pending}\n", encoding="utf-8")
    # prod present in contract → generated; adding staging (absent) → stale.
    r1, u1 = resolve_deployment_readiness(tmp_path, _manifest(
        _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n"))
    assert r1 == "generated" and u1 == 1
    r2, _ = resolve_deployment_readiness(tmp_path, _manifest(
        _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n    staging: {}\n"))
    assert r2 == "stale"


def test_resolve_readiness_no_false_stale_when_contract_untracked(tmp_path):
    # A contract that does NOT track environments must NOT force `stale` (review-fix: empty→None).
    from startd8.scaffold_codegen.deploy_readiness import resolve_deployment_readiness
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "infra-contract.yaml").write_text(
        "bindings:\n  - {name: db, status: bound}\n", encoding="utf-8")  # no environments tracked
    readiness, _ = resolve_deployment_readiness(tmp_path, _manifest(
        _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n    staging: {}\n"))
    assert readiness == "generated"  # not "stale" — can't confirm envs, so no false alarm
