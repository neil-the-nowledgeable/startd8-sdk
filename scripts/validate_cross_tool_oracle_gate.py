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
CHECK_REQUIREMENTS = {
    "oracle_provenance": (
        "Record authorship, commits, Claude-derived portions, and independent "
        "non-Claude review."
    ),
    "evidence_mapping": (
        "Map fixed and adjudicated-open behavior to source traceability evidence."
    ),
    "reviewer_signoff": (
        "Two reviewer sign-offs, including one blinded where practical."
    ),
    "mutant_adequacy": (
        "Every material OPEN dimension has a discriminating single-fault mutant."
    ),
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def oracle_provenance_errors(provenance: dict) -> list[str]:
    """Return errors for provenance fields that a status flag cannot prove."""
    errors = []
    oracle_ref = provenance.get("oracle")
    if not isinstance(oracle_ref, str) or not oracle_ref or not (ROOT / oracle_ref).is_file():
        errors.append("oracle path is missing or unreadable")

    authorship = provenance.get("authorship")
    if not isinstance(authorship, list) or not any(
        isinstance(record, dict) and isinstance(record.get("commits"), list) and record["commits"]
        for record in authorship
    ):
        errors.append("requires an immutable oracle implementation commit")

    if not provenance.get("independent_non_claude_review"):
        errors.append("requires an independent non-Claude review record")

    for path in (
        ROOT / "oracle/test_oracle.py",
        ROOT / "oracle/canonical_cases.py",
    ):
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            errors.append(f"calibration source unreadable: {path.name}")
            continue
        if "runs/" in source:
            errors.append(f"calibration source references authoring-run artifacts: {path.name}")
    return errors


def is_complete_accepting_signoff(signoff: object) -> bool:
    if not isinstance(signoff, dict):
        return False
    required = {
        "reviewer_id",
        "role",
        "blinded",
        "evidence_reviewed",
        "decision",
        "rationale",
        "date",
    }
    return required.issubset(signoff) and signoff["decision"] in {"accept", "accepted"}


def validate() -> dict:
    errors = []
    check_errors = {check_id: [] for check_id in JSON_EVIDENCE}
    evidence = {}
    for check_id, path in JSON_EVIDENCE.items():
        try:
            item = load(path)
        except (OSError, json.JSONDecodeError) as exc:
            message = f"unreadable ({type(exc).__name__})"
            check_errors[check_id].append(message)
            errors.append(f"{check_id}: {message}")
            continue
        evidence[check_id] = item
        if item.get("status") != "accepted":
            message = "status is not accepted"
            check_errors[check_id].append(message)
            errors.append(f"{check_id}: {message}")
        elif check_id == "oracle_provenance":
            for message in oracle_provenance_errors(item):
                check_errors[check_id].append(message)
                errors.append(f"{check_id}: {message}")

    signoffs = evidence.get("reviewer_signoff", {}).get("signoffs", [])
    if len(signoffs) < 2 or any(not is_complete_accepting_signoff(signoff) for signoff in signoffs):
        message = "requires two complete accepting sign-offs"
        check_errors["reviewer_signoff"].append(message)
        errors.append(f"reviewer_signoff: {message}")
    try:
        mutants = load(ROOT / "mutants/manifest.json")
        matrix = (ROOT / "mutants/expected-kill-matrix.csv").read_text(encoding="utf-8").splitlines()
        if mutants.get("status") != "accepted" or len(matrix) <= 1:
            message = "executable accepted mutants and expected-kill rows required"
            check_errors["mutant_adequacy"].append(message)
            errors.append(f"mutant_adequacy: {message}")
    except (OSError, json.JSONDecodeError):
        message = "mutant manifest or kill matrix unreadable"
        check_errors["mutant_adequacy"].append(message)
        errors.append(f"mutant_adequacy: {message}")

    checks = [
        {
            "id": check_id,
            "status": "accepted" if not check_errors[check_id] else "blocked",
            "requirement": CHECK_REQUIREMENTS[check_id],
            "errors": check_errors[check_id],
        }
        for check_id in JSON_EVIDENCE
    ]
    return {
        "status": "accepted" if not errors else "blocked",
        "checks": checks,
        "errors": errors,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-status", action="store_true", help="Update the derived status in validation-gate.json.")
    args = parser.parse_args(argv)
    result = validate()
    if args.sync_status:
        gate = load(GATE)
        gate["status"] = result["status"]
        gate["checks"] = result["checks"]
        gate["validation_errors"] = result["errors"]
        GATE.write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "accepted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
