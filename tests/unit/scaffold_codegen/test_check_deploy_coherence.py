"""M0 — deploy-coherence verdict + check script (REQ-CDP-DEPLOY-6, FR-CND-30).

Covers: severity-tier tagging at source, the (verdict, exit_code) mapping incl. the security→HARD
path (synthetic — no security-ERROR code ships until cloud-native M3), JSON shape, and the script's
fail-closed exit codes end-to-end.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from startd8.scaffold_codegen.coherence import (
    ERROR,
    OPERATIONAL,
    SECURITY,
    WARN,
    CoherenceFinding,
    deploy_coherence_verdict,
    evaluate_coherence,
    finding_to_dict,
)
from startd8.scaffold_codegen.manifest import parse_app_manifest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO_ROOT / "scripts" / "check_deploy_coherence.py"
_SRC = _REPO_ROOT / "src"

DEPLOYED_SQLITE_FILE = """\
app:
  name: demo
persistence:
  path: ./data/app.db
deployment:
  mode: deployed
"""

DEPLOYED_CLEAN = """\
app:
  name: demo
persistence:
  path: postgresql://db.internal/demo
deployment:
  mode: deployed
"""

INSTALLED = """\
app:
  name: demo
deployment:
  mode: installed
"""


# ---- severity-tier tagging (at source) --------------------------------------------------------

def test_findings_carry_severity_tier():
    findings = evaluate_coherence(parse_app_manifest(DEPLOYED_SQLITE_FILE), has_auth_seam=True)
    by_code = {f.code: f for f in findings}
    assert by_code["deployed-sqlite-file"].severity_tier == OPERATIONAL
    # deployed + auth seam + no tenant ⇒ the security-tier (but WARN-severity) isolation warning
    assert by_code["deployed-auth-no-tenant"].severity_tier == SECURITY
    assert by_code["deployed-auth-no-tenant"].severity == WARN


def test_finding_to_dict_always_includes_tier():
    d = finding_to_dict(CoherenceFinding(ERROR, "x", "m", severity_tier=SECURITY))
    assert d == {"severity": "ERROR", "severity_tier": "security", "code": "x", "message": "m"}


# ---- verdict mapping --------------------------------------------------------------------------

def test_verdict_skip_when_not_deployed():
    assert deploy_coherence_verdict((), mode="installed") == ("skip", 2)


def test_verdict_ok_when_deployed_and_clean():
    findings = evaluate_coherence(parse_app_manifest(DEPLOYED_CLEAN), has_auth_seam=True)
    # only the WARN/security auth-no-tenant finding — never blocks
    assert all(f.severity == WARN for f in findings)
    assert deploy_coherence_verdict(findings, mode="deployed") == ("ok", 0)


def test_verdict_soft_on_operational_error():
    findings = evaluate_coherence(parse_app_manifest(DEPLOYED_SQLITE_FILE), has_auth_seam=True)
    assert deploy_coherence_verdict(findings, mode="deployed") == ("soft", 1)


def test_verdict_hard_on_security_error():
    # No security-ERROR code ships until cloud-native M3 (decode-only-no-gateway-ack); the mapping
    # is verified here with a synthetic finding so the HARD path is covered now.
    findings = (CoherenceFinding(ERROR, "synthetic-sec", "m", severity_tier=SECURITY),)
    assert deploy_coherence_verdict(findings, mode="deployed") == ("hard", 3)


def test_security_warn_does_not_hard_abort():
    # a security-tier WARN (auth-no-tenant) must NOT become HARD — single-owner deploys stay legal
    findings = (CoherenceFinding(WARN, "deployed-auth-no-tenant", "m", severity_tier=SECURITY),)
    assert deploy_coherence_verdict(findings, mode="deployed") == ("ok", 0)


# ---- script end-to-end (exit codes are the cross-repo contract) --------------------------------

def _run(project_dir: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    return subprocess.run(
        [sys.executable, str(_SCRIPT), str(project_dir), "--json"],
        capture_output=True, text=True, env=env,
    )


def _write(tmp_path: Path, content: str) -> Path:
    (tmp_path / "app.yaml").write_text(content, encoding="utf-8")
    return tmp_path


def test_script_soft_exit1(tmp_path):
    proc = _run(_write(tmp_path, DEPLOYED_SQLITE_FILE))
    assert proc.returncode == 1, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["verdict"] == "soft"
    assert payload["mode"] == "deployed"
    assert payload["schemaVersion"]["major"] == 1
    assert any(f["code"] == "deployed-sqlite-file" for f in payload["findings"])


def test_script_ok_exit0(tmp_path):
    proc = _run(_write(tmp_path, DEPLOYED_CLEAN))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["verdict"] == "ok"


def test_script_installed_skips_exit2(tmp_path):
    proc = _run(_write(tmp_path, INSTALLED))
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["verdict"] == "skip"


def test_script_no_app_yaml_skips_exit2(tmp_path):
    proc = _run(tmp_path)  # empty dir
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["verdict"] == "skip"


def test_script_malformed_app_yaml_fails_closed_exit3(tmp_path):
    _write(tmp_path, "deployment: {mode: deployed\n  oops: [unclosed")
    proc = _run(tmp_path)
    assert proc.returncode == 3, proc.stderr
    assert json.loads(proc.stdout)["verdict"] == "hard"
