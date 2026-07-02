"""A8 — `startd8 wireframe` surfaces the deployment mode + posture + coherence (FR-CFG-6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.wireframe import Status, build_wireframe_plan, load_assembly_inputs

pytestmark = pytest.mark.unit


def _plan(tmp_path: Path, app_yaml: str):
    p = tmp_path / "app.yaml"
    p.write_text(app_yaml, encoding="utf-8")
    return build_wireframe_plan(load_assembly_inputs(overrides={"app": p}, project_root=tmp_path))


def _details(section):
    return {i.label: i.detail for i in section.items}


# A coherent deployed manifest: postgres persistence + trust_gateway ack clears the FR-CND-6
# decode-only-no-gateway ERROR (leaving only the no-tenant WARN → section stays PLANNED).
_COHERENT_DEPLOYED = (
    "deployment:\n  mode: deployed\n"
    "persistence:\n  path: postgresql://db/app\n"
    "deploy:\n  trust_gateway: true\n"
)


def test_deployment_section_deployed_posture(tmp_path):
    plan = _plan(tmp_path, _COHERENT_DEPLOYED)
    sec = plan.section("deployment")
    assert sec is not None and sec.title == "Deployment mode" and sec.status == Status.PLANNED
    d = _details(sec)
    assert d["mode"] == "deployed"
    assert "0.0.0.0" in d["bind"]
    assert "shared DB" in d["persistence"] and "migrations" in d["schema-init"]


def test_deployment_section_surfaces_environments_and_readiness(tmp_path):
    # FR-CDA-2: deployed + declared environments surfaces env names, the deploy/ artifact set, and
    # readiness. No deploy/ tree on disk here → declared-not-generated.
    app = _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n    staging: {}\n"
    d = _details(_plan(tmp_path, app).section("deployment"))
    assert d["environments"] == "prod, staging"  # sorted (R1-S7)
    assert "deploy/ files" in d["deploy-artifacts"]
    assert d["readiness"] == "declared-not-generated"


def test_deployment_section_readiness_generated_and_stale(tmp_path):
    # deploy/ tree + contract present → generated; a declared env absent from the contract → stale.
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "infra-contract.yaml").write_text(
        "environments:\n  prod: {}\nbindings: []\n", encoding="utf-8")
    app = _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n"
    d = _details(_plan(tmp_path, app).section("deployment"))
    assert d["readiness"] == "generated"
    assert d["unbound-bindings"] == "0"
    # add a second env not in the contract → stale
    app2 = _COHERENT_DEPLOYED + "  environments:\n    prod: {}\n    staging: {}\n"
    d2 = _details(_plan(tmp_path, app2).section("deployment"))
    assert d2["readiness"] == "stale"


def test_deployment_section_installed_has_no_deploy_items(tmp_path):
    # SOTTO: installed mode emits none of the FR-CDA-2 additive items (byte-identical to pre-CDA).
    d = _details(_plan(tmp_path, "app:\n  name: d\n").section("deployment"))
    for absent in ("environments", "deploy-artifacts", "readiness", "unbound-bindings"):
        assert absent not in d


def test_deployment_section_installed_default(tmp_path):
    plan = _plan(tmp_path, "app:\n  name: d\n")  # no deployment block -> installed
    d = _details(plan.section("deployment"))
    assert d["mode"] == "installed"
    assert "127.0.0.1" in d["bind"]
    assert "SQLite" in d["persistence"]


def test_deployment_section_surfaces_coherence_error(tmp_path):
    # deployed + the default SQLite persistence -> coherence ERROR (advisory in wireframe).
    sec = _plan(tmp_path, "deployment:\n  mode: deployed\n").section("deployment")
    assert sec.status == Status.INVALID
    labels = [i.label for i in sec.items]
    assert "coherence:deployed-sqlite-file" in labels
    assert sec.consequence  # non-empty: explains generate backend will refuse
