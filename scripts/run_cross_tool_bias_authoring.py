#!/usr/bin/env python3
"""Gate external cross-tool authoring runs behind the frozen experiment controls.

Dry-run emits the deterministic run plan. ``--run`` is intentionally fail-closed until every
pre-registered authoring tool and the independent oracle/mutant admission gate are accepted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = REPO / "scripts/prepare_cross_tool_bias_experiment.py"
GATE_PATH = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai/oracle/validation-gate.json"

spec = importlib.util.spec_from_file_location("bias_prepare", PREPARE_SCRIPT)
assert spec and spec.loader
prepare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prepare
spec.loader.exec_module(prepare)


def oracle_gate_passes(path: Path = GATE_PATH) -> bool:
    try:
        gate = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return gate.get("status") == "accepted" and all(
        check.get("status") == "accepted" for check in gate.get("checks", [])
    )


def build_authoring_plan(manifest: dict, output_dir: Path) -> dict:
    schedule = prepare.build_schedule(manifest)
    return {
        "experiment_id": manifest["experiment_id"],
        "run_count": len(schedule),
        "raw_capture_root": str(output_dir / "raw"),
        "normalized_artifact_root": str(output_dir / "normalized"),
        "retry_policy": manifest["authoring"]["retry_policy"],
        "runs": schedule,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=prepare.DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path,
                        default=Path("/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1"))
    parser.add_argument("--run", action="store_true", help="Require every preflight gate before invoking any authoring tool.")
    args = parser.parse_args(argv)
    try:
        manifest = prepare._load_manifest(args.manifest)
        prepare.validate_manifest(manifest)
        prepare._assert_clean_workspace(args.output_dir, manifest["execution_controls"])
    except prepare.ManifestError as exc:
        print(f"authoring blocked: {exc}", file=sys.stderr)
        return 2

    tools = prepare.preflight_tools(manifest)
    unavailable = [tool["tool_id"] for tool in tools if not tool["available"]]
    if args.run and unavailable:
        print(f"authoring blocked: required authoring tools unavailable: {', '.join(unavailable)}", file=sys.stderr)
        return 2
    if args.run and not oracle_gate_passes():
        print("authoring blocked: independent oracle/mutant validation gate is not accepted", file=sys.stderr)
        return 2

    print(json.dumps({"mode": "dry_run" if not args.run else "gated", "tools": tools,
                      "plan": build_authoring_plan(manifest, args.output_dir)}, indent=2))
    if args.run:
        print("authoring invocation remains disabled until reviewed command templates are added", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
