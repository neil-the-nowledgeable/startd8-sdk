#!/usr/bin/env python3
"""Deploy-coherence gate check for cap-dev-pipe integration (REQ-CDP-DEPLOY-6, FR-CND-30).

Runs the deployment-mode coherence guard (``scaffold_codegen.coherence``) over a project's
``app.yaml`` and emits a versioned, machine-readable verdict. The cap-dev-pipe deploy-coherence
gate consumes this via returncode + JSON (the ``check_seed_quality.py`` Keiyaku idiom) — so the
generation orchestrator can fail-closed on a ``deployed`` run WITHOUT importing SDK code.

Exit codes (the contract):
    0 — ok    : deployed posture, no blocking finding
    1 — soft  : deployed posture, operational ERROR (overridable downstream)
    2 — skip  : not a deployed posture (no ``deploy/`` tree to gate) / no ``app.yaml``
    3 — hard  : security-critical ERROR (NON-overridable downstream), OR a fail-closed condition
                (malformed ``app.yaml`` / unexpected error — we cannot certify a deployed app, so deny)

Fail-closed by design: anything that prevents certifying coherence on a deployed posture exits 3,
never silently 0/2. (The downstream consumer additionally fail-closes on missing script / malformed
JSON / schemaVersion major-skew — REQ-CDP-DEPLOY-10.)

Usage::

    python3 scripts/check_deploy_coherence.py /path/to/project
    python3 scripts/check_deploy_coherence.py . --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

SCHEMA_VERSION = {"major": 1, "minor": 0}


def _find_app_yaml(project_root: Path) -> Optional[Path]:
    """Locate ``app.yaml`` (mirrors the ScaffoldFileProvider discovery order)."""
    for candidate in (project_root / "app.yaml", project_root / "prisma" / "app.yaml"):
        if candidate.is_file():
            return candidate
    return None


def _count_unbound_bindings(project_root: Path) -> Optional[int]:
    """Best-effort: count operator bindings still unbound in ``deploy/infra-contract.yaml``.

    Returns ``None`` when the contract is absent or unparseable (the cloud-native infra-contract,
    FR-CND-26, may not exist yet) — the gate treats ``None`` as "unknown", never as zero.
    """
    contract = project_root / "deploy" / "infra-contract.yaml"
    if not contract.is_file():
        return None
    try:
        import yaml  # lazy: only needed when a contract exists

        data = yaml.safe_load(contract.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    bindings = data.get("bindings") or data.get("operator_bindings") or []
    if not isinstance(bindings, list):
        return None
    bound = {"bound", "satisfied", "provided", "provided-ok"}
    return sum(1 for b in bindings if isinstance(b, dict) and str(b.get("status", "")).lower() not in bound)


def evaluate(project_root: Path) -> tuple[dict, int]:
    """Produce the (verdict_payload, exit_code). Pure except for reading the project files."""
    from startd8.scaffold_codegen.coherence import (
        deploy_coherence_verdict,
        evaluate_coherence,
        finding_to_dict,
    )
    from startd8.scaffold_codegen.manifest import parse_app_manifest

    app_yaml = _find_app_yaml(project_root)
    if app_yaml is None:
        # Nothing to evaluate — no app.yaml means no deployed posture to gate.
        return ({"schemaVersion": SCHEMA_VERSION, "verdict": "skip", "mode": None,
                 "findings": [], "unbound_bindings": None,
                 "reason": "no app.yaml found"}, 2)

    try:
        manifest = parse_app_manifest(app_yaml.read_text(encoding="utf-8"))
    except Exception as exc:  # malformed app.yaml ⇒ cannot certify a deployed posture ⇒ fail-closed
        return ({"schemaVersion": SCHEMA_VERSION, "verdict": "hard", "mode": None,
                 "findings": [], "unbound_bindings": None,
                 "reason": f"app.yaml unparseable (fail-closed): {exc}"}, 3)

    mode = manifest.deployment_mode
    # The auth seam is emitted in deployed mode (FR-IDN-2); tenancy is declared in app.yaml.
    findings = evaluate_coherence(
        manifest, has_auth_seam=(mode == "deployed"), has_tenant=manifest.has_tenant
    )
    verdict, exit_code = deploy_coherence_verdict(findings, mode=mode)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "verdict": verdict,
        "mode": mode,
        "findings": [finding_to_dict(f) for f in findings],
        "unbound_bindings": _count_unbound_bindings(project_root),
    }
    return payload, exit_code


def _print_human(payload: dict) -> None:
    verdict = payload["verdict"]
    mode = payload.get("mode")
    print(f"deploy-coherence: {verdict.upper()} (mode={mode})")
    for f in payload.get("findings", []):
        print(f"  [{f['severity']}/{f['severity_tier']}] {f['code']}: {f['message']}")
    ub = payload.get("unbound_bindings")
    if ub is not None:
        print(f"  unbound operator bindings: {ub}")
    if payload.get("reason"):
        print(f"  ({payload['reason']})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy-coherence gate check (REQ-CDP-DEPLOY-6).")
    parser.add_argument("project", nargs="?", default=".", help="project root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="emit the machine-readable verdict")
    args = parser.parse_args()

    project_root = Path(args.project).resolve()
    try:
        payload, exit_code = evaluate(project_root)
    except Exception as exc:  # any unexpected error ⇒ fail-closed (deny), never a silent pass
        payload = {"schemaVersion": SCHEMA_VERSION, "verdict": "hard", "mode": None,
                   "findings": [], "unbound_bindings": None,
                   "reason": f"unexpected error (fail-closed): {exc}"}
        exit_code = 3

    if args.json:
        print(json.dumps(payload))
    else:
        _print_human(payload)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
