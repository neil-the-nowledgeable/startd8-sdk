#!/usr/bin/env python3
"""Derive the oracle/mutant gate status from auditable evidence files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai"
GATE = ROOT / "oracle/validation-gate.json"
JSON_EVIDENCE = {
    "oracle_provenance": ROOT / "oracle/oracle-provenance.json",
    "evidence_mapping": ROOT / "oracle/fixed-open-evidence.json",
    "reviewer_signoff": ROOT / "oracle/reviewer-signoffs.json",
    "mutant_adequacy": ROOT / "mutants/adequacy-report.json",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate() -> dict:
    errors = []
    for check_id, path in JSON_EVIDENCE.items():
        try:
            item = load(path)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{check_id}: unreadable ({type(exc).__name__})")
            continue
        if item.get("status") != "accepted":
            errors.append(f"{check_id}: status is not accepted")
    try:
        signoffs = load(JSON_EVIDENCE["reviewer_signoff"]).get("signoffs", [])
    except (OSError, json.JSONDecodeError):
        signoffs = []
    required = {"reviewer_id", "role", "blinded", "evidence_reviewed", "decision", "rationale", "date"}
    if len(signoffs) < 2 or any(not required.issubset(signoff) for signoff in signoffs):
        errors.append("reviewer_signoff: requires two complete sign-offs")
    try:
        mutants = load(ROOT / "mutants/manifest.json")
        matrix = (ROOT / "mutants/expected-kill-matrix.csv").read_text(encoding="utf-8").splitlines()
        if mutants.get("status") != "accepted" or len(matrix) <= 1:
            errors.append("mutant_adequacy: executable accepted mutants and expected-kill rows required")
    except (OSError, json.JSONDecodeError):
        errors.append("mutant_adequacy: mutant manifest or kill matrix unreadable")
    return {"status": "accepted" if not errors else "blocked", "errors": errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-status", action="store_true", help="Update the derived status in validation-gate.json.")
    args = parser.parse_args(argv)
    result = validate()
    if args.sync_status:
        gate = load(GATE)
        gate["status"] = result["status"]
        gate["validation_errors"] = result["errors"]
        GATE.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
