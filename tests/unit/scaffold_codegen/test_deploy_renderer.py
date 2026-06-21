"""M1 — cloud-native deploy/ manifest renderers (CLOUD_NATIVE_DEPLOY FR-CND-1/3/5/12/13/16/18).

Vendor-neutral, byte-stable, drift-owned. Plus the cross-seam test: render the deploy tree, then run
the SDK check_deploy_coherence verdict over the same project (M0+M3+M1 end to end).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

from startd8.scaffold_codegen import render_scaffold
from startd8.scaffold_codegen.deploy_renderer import render_deploy_tree
from startd8.scaffold_codegen.drift import is_owned_scaffold_file, scaffold_in_sync

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "check_deploy_coherence.py"
_SRC = _REPO_ROOT / "src"

DEPLOYED = (
    "app:\n  name: My App!!\n  package: app\n"   # name forces DNS-1123 sanitization
    "deployment:\n  mode: deployed\n"
    "persistence:\n  path: postgresql://db/app\n"
    "deploy:\n  trust_gateway: true\n  target_cloud: gke\n  secrets:\n    backend: eso-doppler\n"
)
INSTALLED = "app:\n  name: demo\ndeployment:\n  mode: installed\n"

# vendor-neutral apiVersion allowlist (FR-CND-28); a vendor CRD here would be a leak.
_ALLOWED_API = {
    "apps/v1", "v1",
    "gateway.networking.k8s.io/v1",
    "networking.k8s.io/v1",
    "external-secrets.io/v1beta1",
}
_K8S_FILES = [
    "deploy/deployment.yaml", "deploy/service.yaml", "deploy/serviceaccount.yaml",
    "deploy/configmap.yaml", "deploy/externalsecret.yaml", "deploy/httproute.yaml",
    "deploy/networkpolicy.yaml",
]


def _tree(text=DEPLOYED):
    return dict(render_deploy_tree(text))


# ---- emission gating --------------------------------------------------------------------------

def test_installed_emits_no_deploy_tree():
    assert render_deploy_tree(INSTALLED) == ()


def test_deployed_emits_full_tree():
    paths = set(_tree())
    assert paths == set(_K8S_FILES) | {"deploy/infra-contract.yaml"}


def test_render_scaffold_includes_deploy_only_when_deployed():
    deployed_paths = {p for p, _ in render_scaffold(DEPLOYED)}
    installed_paths = {p for p, _ in render_scaffold(INSTALLED)}
    assert "deploy/deployment.yaml" in deployed_paths
    assert not any(p.startswith("deploy/") for p in installed_paths)  # SOTTO: absent when installed


# ---- validity / determinism / vendor-neutrality -----------------------------------------------

def test_all_manifests_parse_as_yaml():
    for path, text in _tree().items():
        doc = yaml.safe_load(text)  # # header comments are valid YAML
        assert isinstance(doc, dict), path


def test_apiversions_are_vendor_neutral():
    for path in _K8S_FILES:
        doc = yaml.safe_load(_tree()[path])
        assert doc["apiVersion"] in _ALLOWED_API, (path, doc["apiVersion"])


def test_byte_stable():
    assert render_deploy_tree(DEPLOYED) == render_deploy_tree(DEPLOYED)


def test_dns1123_object_names():
    dep = yaml.safe_load(_tree()["deploy/deployment.yaml"])
    assert dep["metadata"]["name"] == "my-app"  # "My App!!" → DNS-1123


# ---- security / contract field checks ---------------------------------------------------------

def test_deployment_hardened_and_probed():
    dep = yaml.safe_load(_tree()["deploy/deployment.yaml"])
    pod = dep["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["automountServiceAccountToken"] is False
    c = pod["containers"][0]
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert c["securityContext"]["allowPrivilegeEscalation"] is False
    assert c["readinessProbe"]["httpGet"]["path"] == "/health"
    assert c["livenessProbe"]["httpGet"]["path"] == "/health/live"


def test_service_is_clusterip():
    assert yaml.safe_load(_tree()["deploy/service.yaml"])["spec"]["type"] == "ClusterIP"


def test_externalsecret_owner_and_refresh():
    es = yaml.safe_load(_tree()["deploy/externalsecret.yaml"])
    assert es["spec"]["target"]["creationPolicy"] == "Owner"
    assert es["spec"]["refreshInterval"] == "1h"


def test_httproute_has_explicit_hostnames_not_wildcard():
    hr = yaml.safe_load(_tree()["deploy/httproute.yaml"])
    assert hr["spec"]["hostnames"] and "*" not in hr["spec"]["hostnames"]


def test_networkpolicy_ingress_and_egress():
    np = yaml.safe_load(_tree()["deploy/networkpolicy.yaml"])
    assert set(np["spec"]["policyTypes"]) == {"Ingress", "Egress"}


def test_infra_contract_versioned_with_bindings_and_prereqs():
    ic = yaml.safe_load(_tree()["deploy/infra-contract.yaml"])
    assert ic["schemaVersion"]["major"] == 1
    assert any(b["kind"] == "secretstore" for b in ic["bindings"])
    assert any(p["name"] == "cni-networkpolicy-enforcement" for p in ic["prerequisites"])


# ---- drift ownership --------------------------------------------------------------------------

def test_deploy_files_are_drift_owned_and_in_sync():
    for path, text in _tree().items():
        assert is_owned_scaffold_file(text), path
        assert scaffold_in_sync(DEPLOYED, text) is True, path
    # tamper → drift detected
    tampered = _tree()["deploy/service.yaml"].replace("ClusterIP", "LoadBalancer")
    assert scaffold_in_sync(DEPLOYED, tampered) is False


# ---- cross-seam: render tree → SDK coherence verdict (M0+M3+M1) --------------------------------

def _run_check(project_dir):
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(project_dir), "--json"],
        capture_output=True, text=True, env=env,
    )


def test_cross_seam_gatewayed_app_passes(tmp_path):
    (tmp_path / "app.yaml").write_text(DEPLOYED, encoding="utf-8")
    for rel, text in render_deploy_tree(DEPLOYED):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    proc = _run_check(tmp_path)
    assert proc.returncode == 0, proc.stderr  # trust_gateway acked → ok
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == "ok"
    assert payload["unbound_bindings"] is not None and payload["unbound_bindings"] >= 1


def test_cross_seam_no_gateway_app_hard_fails(tmp_path):
    no_gw = DEPLOYED.replace("  trust_gateway: true\n", "")
    (tmp_path / "app.yaml").write_text(no_gw, encoding="utf-8")
    proc = _run_check(tmp_path)
    assert proc.returncode == 3, proc.stderr  # decode-only-no-gateway-ack → HARD
    assert json.loads(proc.stdout)["verdict"] == "hard"
