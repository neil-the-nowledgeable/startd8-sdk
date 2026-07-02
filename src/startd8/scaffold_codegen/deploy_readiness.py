"""Deployment coherence + readiness — the single in-process source of the deploy verdict payload.

This module is the ONE implementation of "how many operator bindings are unbound?" and "what is the
deploy-coherence verdict?" (R1-F2 single-source). Three call sites consume it, so they can never
diverge:

- ``scripts/check_deploy_coherence.py`` — the subprocess Keiyaku for cap-dev-pipe AND the Concierge
  ``check_deploy_coherence`` MCP tool (FR-CDA-5): runs this via ``python -m``/argv, reads returncode
  + JSON, never importing SDK internals itself.
- ``concierge.core.build_assess`` — surfaces the payload in-process (FR-CDA-1): identical values,
  no second reader of ``deploy/infra-contract.yaml``.
- ``wireframe.plan._deployment_section`` — surfaces the per-env binding count in-process (FR-CDA-2).

Reading-only, deterministic, $0 (no LLM). Fail-closed: any condition that prevents certifying a
deployed posture yields ``verdict="hard"`` with a ``reason`` (never a silent pass).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

SCHEMA_VERSION = {"major": 1, "minor": 0}

# <repo>/scripts/check_deploy_coherence.py — this file is src/startd8/scaffold_codegen/deploy_readiness.py
_REPO_ROOT = Path(__file__).resolve().parents[3]
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "check_deploy_coherence.py"
# returncode → verdict (the script's Keiyaku, mirrored so a non-zero code is mapped, never swallowed).
_RC_VERDICT = {0: "ok", 1: "soft", 2: "skip", 3: "hard"}


def _hard_payload(reason: str) -> dict:
    """The fail-closed verdict (R1-S8): a structured ``hard``, never a crash or silent pass."""
    return {"schemaVersion": SCHEMA_VERSION, "verdict": "hard", "mode": None,
            "findings": [], "unbound_bindings": None, "reason": reason}


def run_deploy_gate_subprocess(
    project_root, *, script_path: Optional[Path] = None, timeout: float = 60.0
) -> dict:
    """Run the deploy-coherence gate via **subprocess** and return the JSON payload (FR-CDA-5).

    This is the Keiyaku boundary the Concierge MCP tool uses: argv is exactly ``[python, script,
    project, --json]`` (no mutating flag exists or is reachable — FR-CDA-6/R1-F1). The returncode
    (0 ok / 1 soft / 2 skip / 3 hard) is mapped, never swallowed. Fail-closed (R1-S8): a missing or
    unstartable script / unparseable output / timeout degrades to a structured ``hard`` with a
    reason. Surfaces only the script payload (names/counts/status) — never secret values (R1-S9).
    """
    script = Path(script_path) if script_path is not None else _GATE_SCRIPT
    if not script.is_file():
        return _hard_payload(f"deploy-coherence script not found at {script} (fail-closed)")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_REPO_ROOT / "src")] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(script), str(project_root), "--json"],
            capture_output=True, text=True, env=env, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return _hard_payload("deploy-coherence gate timed out (fail-closed)")
    except Exception as exc:  # unstartable subprocess → fail-closed, never a crash
        return _hard_payload(f"gate could not run (fail-closed): {type(exc).__name__}: {exc}")
    try:
        payload = json.loads((proc.stdout or "").strip() or "{}")
    except json.JSONDecodeError:
        return _hard_payload(
            f"unparseable gate output (rc={proc.returncode}): {(proc.stderr or proc.stdout)[:400]}")
    if not isinstance(payload, dict):
        return _hard_payload(f"gate returned non-object payload (rc={proc.returncode})")
    # The payload verdict is authoritative; ensure the returncode is mapped when absent.
    payload.setdefault("verdict", _RC_VERDICT.get(proc.returncode, "hard"))
    return payload

# Readiness states (FR-CDA-1 v0.4). Derived from (deployed-declared) × (deploy/ tree present) ×
# (infra-contract parseable) — NOT from the ``unbound_bindings is None`` sentinel alone, which is
# broader ("unknown": absent OR unparseable) and would mis-report a broken contract as ``generated``.
READINESS_NOT_DECLARED = "not-declared"            # no deployed posture (installed / no deploy block)
READINESS_DECLARED_NOT_GENERATED = "declared-not-generated"  # deployed, but no deploy/ tree yet
READINESS_GENERATED = "generated"                  # deployed, deploy/ tree + parseable contract
READINESS_UNKNOWN = "unknown"                      # deployed, tree present but contract absent/unparseable


def find_app_yaml(project_root: Path) -> Optional[Path]:
    """Locate ``app.yaml`` (mirrors the ScaffoldFileProvider discovery order)."""
    for candidate in (project_root / "app.yaml", project_root / "prisma" / "app.yaml"):
        if candidate.is_file():
            return candidate
    return None


def _contract_path(project_root: Path) -> Path:
    return project_root / "deploy" / "infra-contract.yaml"


def _load_contract(project_root: Path) -> Optional[dict]:
    """Parse ``deploy/infra-contract.yaml`` once. ``None`` = absent / unparseable / non-mapping."""
    contract = _contract_path(project_root)
    if not contract.is_file():
        return None
    try:
        import yaml  # lazy: only needed when a contract exists

        data = yaml.safe_load(contract.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _unbound_from_data(data: Optional[dict]) -> Optional[int]:
    """Unbound-binding count from an already-parsed contract. ``None`` = unknown."""
    if data is None:
        return None
    bindings = data.get("bindings") or data.get("operator_bindings") or []
    if not isinstance(bindings, list):
        return None
    bound = {"bound", "satisfied", "provided", "provided-ok"}
    return sum(
        1 for b in bindings if isinstance(b, dict) and str(b.get("status", "")).lower() not in bound
    )


def _envs_from_data(data: Optional[dict]) -> Optional[set]:
    """Environment names an already-parsed contract represents. ``None`` = not tracked / unknown
    (so staleness is *not* asserted when the contract simply doesn't model environments — avoids a
    false-positive ``stale``)."""
    if data is None:
        return None
    envs: set = set()
    raw = data.get("environments")
    if isinstance(raw, dict):
        envs |= set(raw.keys())
    elif isinstance(raw, list):
        envs |= {e for e in raw if isinstance(e, str)}
    for b in (data.get("bindings") or data.get("operator_bindings") or []):
        if isinstance(b, dict) and isinstance(b.get("environment"), str):
            envs.add(b["environment"])
    return envs or None  # empty ⇒ "not tracked", not "zero envs"


def count_unbound_bindings(project_root: Path) -> Optional[int]:
    """Count operator bindings still unbound in ``deploy/infra-contract.yaml`` (``None`` = unknown)."""
    return _unbound_from_data(_load_contract(project_root))


def contract_environments(project_root: Path) -> Optional[set]:
    """The environment names represented in the contract (``None`` = absent/unparseable/not tracked)."""
    return _envs_from_data(_load_contract(project_root))


def resolve_deployment_readiness(project_root, manifest) -> Tuple[str, Optional[int]]:
    """The SINGLE derivation of ``(readiness, unbound_bindings)`` for a manifest — used by BOTH
    ``concierge assess`` (FR-CDA-1) and the wireframe section (FR-CDA-2) so the FR-CDA-8 staleness
    rule can't diverge between them. Reads the contract at most once.

    ``installed`` → ``not-declared``. ``deployed`` → ``declared-not-generated`` (no ``deploy/`` tree)
    / ``generated`` / ``unknown`` (tree but no/unparseable contract) / ``stale`` (declared envs ⊄
    the contract's tracked envs, FR-CDA-8).
    """
    root = Path(project_root)
    mode = getattr(manifest, "deployment_mode", None)
    if mode != "deployed":
        return READINESS_NOT_DECLARED, None
    if not (root / "deploy").is_dir():
        return READINESS_DECLARED_NOT_GENERATED, None
    data = _load_contract(root)
    if data is None:
        return READINESS_UNKNOWN, None
    unbound = _unbound_from_data(data)
    readiness = READINESS_GENERATED
    if getattr(manifest, "has_environments", False):
        envs = _envs_from_data(data)
        if envs is not None and not set(manifest.deploy_environments) <= envs:
            readiness = "stale"
    return readiness, unbound


def readiness_state(project_root: Path, *, mode: Optional[str]) -> str:
    """The 4-state deployment readiness (FR-CDA-1 v0.4).

    ``installed`` / unknown mode → ``not-declared`` (no deployed posture to be *ready* for; the
    ``deploy/`` tree is not expected). ``deployed`` → tri-state on the on-disk generation:

    - no ``deploy/`` tree            → ``declared-not-generated``
    - tree + parseable contract      → ``generated``
    - tree but absent/unparseable    → ``unknown`` (advisory; MUST NOT read as ``generated``)

    ``stale`` (declared envs ⊄ contract envs, FR-CDA-8) is layered on ``generated`` by the caller.
    """
    if mode != "deployed":
        return READINESS_NOT_DECLARED
    deploy_dir = project_root / "deploy"
    if not deploy_dir.is_dir():
        return READINESS_DECLARED_NOT_GENERATED
    if not _contract_path(project_root).is_file() or _load_contract(project_root) is None:
        return READINESS_UNKNOWN
    return READINESS_GENERATED


def evaluate_deploy_coherence(project_root: Path) -> Tuple[dict, int]:
    """Produce ``(verdict_payload, exit_code)`` — the single verdict source.

    Exit codes (the cap-dev-pipe Keiyaku contract, preserved from the original script):
        0 ok · 1 soft · 2 skip (not deployed / no app.yaml) · 3 hard (security ERROR or fail-closed).
    Pure except for reading the project files. Malformed ``app.yaml`` ⇒ fail-closed ``hard``.
    """
    from startd8.scaffold_codegen.coherence import (
        deploy_coherence_verdict,
        evaluate_coherence,
        finding_to_dict,
    )
    from startd8.scaffold_codegen.manifest import parse_app_manifest

    app_yaml = find_app_yaml(project_root)
    if app_yaml is None:
        return (
            {
                "schemaVersion": SCHEMA_VERSION, "verdict": "skip", "mode": None,
                "findings": [], "unbound_bindings": None, "readiness": READINESS_NOT_DECLARED,
                "reason": "no app.yaml found",
            },
            2,
        )

    try:
        manifest = parse_app_manifest(app_yaml.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed app.yaml ⇒ cannot certify a deployed posture ⇒ fail-closed
        return (
            {
                "schemaVersion": SCHEMA_VERSION, "verdict": "hard", "mode": None,
                "findings": [], "unbound_bindings": None, "readiness": READINESS_UNKNOWN,
                "reason": f"app.yaml unparseable (fail-closed): {exc}",
            },
            3,
        )

    mode = manifest.deployment_mode
    # The auth seam is emitted in deployed mode (FR-IDN-2); tenancy is declared in app.yaml.
    findings = evaluate_coherence(
        manifest, has_auth_seam=(mode == "deployed"), has_tenant=manifest.has_tenant
    )
    verdict, exit_code = deploy_coherence_verdict(findings, mode=mode)
    # Single derivation of readiness + unbound (staleness-aware), shared with assess/wireframe.
    readiness, unbound = resolve_deployment_readiness(project_root, manifest)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "verdict": verdict,
        "mode": mode,
        "findings": [finding_to_dict(f) for f in findings],
        "unbound_bindings": unbound,
        "readiness": readiness,
    }
    return payload, exit_code
