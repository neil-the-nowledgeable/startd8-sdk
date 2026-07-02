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

# The verdict logic lives in the SDK (single source, R1-F2) so the Concierge assess/wireframe
# surfaces and this subprocess produce byte-identical payloads. This script is the subprocess
# Keiyaku boundary: returncode + JSON, so a consumer (cap-dev-pipe orchestrator, the MCP tool)
# never imports SDK code itself.
from startd8.scaffold_codegen.deploy_readiness import SCHEMA_VERSION, evaluate_deploy_coherence


def evaluate(project_root: Path) -> tuple[dict, int]:
    """Delegate to the SDK single-source evaluator (kept as a name for existing callers/tests)."""
    return evaluate_deploy_coherence(project_root)


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
