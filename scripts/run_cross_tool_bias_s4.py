#!/usr/bin/env python3
"""Preflight S4 suite-authoring analysis without executing untrusted suites.

The preflight is deliberately fail-closed.  It permits only an accepted promoted
batch and an accepted oracle/mutant gate, creates auditable placeholder matrices,
and requires a reviewed isolated bridge before model-authored Python is executed.
"""
from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
AUDIT_ROOT = REPO / "docs/design/benchmark-bias-audit/bias_audit_openai"
DEFAULT_STORE_ROOT = REPO / ".startd8/bias-audit-store"
DEFAULT_BATCH_ID = "pricing-cross-tool-authoring-v1"
DEFAULT_RESULTS_ROOT = AUDIT_ROOT / "analysis/s4-results"
DEFAULT_GATE = AUDIT_ROOT / "oracle/validation-gate.json"
DEFAULT_MUTANTS = AUDIT_ROOT / "mutants/manifest.json"
DEFAULT_PRE_REGISTRATION = AUDIT_ROOT / "analysis/s4-pre-registration.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is unreadable: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object: {path}")
    return value


def accepted_suite_rows(ledger: dict) -> list[dict]:
    return [
        row
        for row in ledger.get("runs", [])
        if row.get("status") == "accepted" and row.get("experiment") == "suite_author"
    ]


def declared_bridge_contract(suite_path: Path, manifest_path: Path) -> dict:
    """Describe a declared adapter convention without importing model-authored code."""
    try:
        tree = ast.parse(suite_path.read_text(encoding="utf-8"), filename=str(suite_path))
        functions = sorted(node.name for node in tree.body if isinstance(node, ast.FunctionDef))
    except (OSError, SyntaxError) as exc:
        return {"status": "invalid_execution", "detail": f"static_parse_failed:{type(exc).__name__}"}

    try:
        manifest = load_json(manifest_path, "suite manifest")
    except ValueError as exc:
        return {"status": "invalid_execution", "detail": str(exc)}

    declared = [key for key in ("adapter_contract", "invoker_contract", "harness_notes") if key in manifest]
    conventions = [
        name
        for name in ("configure", "bind_invoker", "run_all", "run_case", "run_ok_cases", "run_invalid_cases")
        if name in functions
    ]
    if not declared and not conventions:
        return {
            "status": "not_executable",
            "detail": "no declared adapter/invoker contract; self-check-only suites cannot be S4 evidence",
            "declared_manifest_fields": declared,
            "conventions": conventions,
        }
    return {
        "status": "bridge_required",
        "detail": "declared contract found; no reviewed isolated S4 bridge is installed",
        "declared_manifest_fields": declared,
        "conventions": conventions,
    }


def target_inventory(manifest: dict, manifest_path: Path) -> list[dict]:
    targets = [{"target_id": "reference_oracle", "status": "accepted"}]
    for mutant in manifest.get("mutants", []):
        if mutant.get("status", manifest.get("status")) != "accepted":
            continue
        source = mutant.get("source") or mutant.get("path")
        record = {"target_id": mutant.get("id", "unnamed_mutant"), "status": "accepted"}
        if isinstance(source, str):
            candidate = manifest_path.parent / source
            record["source"] = source
            if candidate.is_file():
                record["sha256"] = sha256(candidate)
        targets.append(record)
    return targets


def write_matrices(results_root: Path, suite_rows: list[dict], targets: list[dict]) -> None:
    results_root.mkdir(parents=True, exist_ok=True)
    ids = [row["run_id"] for row in suite_rows]
    with (results_root / "mutant_kill_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["suite_run_id", "execution_status", *[target["target_id"] for target in targets]])
        for suite_id in ids:
            writer.writerow([suite_id, "not_executed", *["not_executed" for _ in targets]])
    with (results_root / "suite_equivalence_matrix.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["suite_run_id", *ids])
        for suite_id in ids:
            writer.writerow([suite_id, *["not_executed" for _ in ids]])


def run_preflight(
    *, store_root: Path, batch_id: str, results_root: Path, gate_path: Path,
    mutants_path: Path, pre_registration_path: Path,
) -> tuple[int, dict]:
    errors: list[str] = []
    try:
        pre_registration = load_json(pre_registration_path, "S4 pre-registration")
    except ValueError as exc:
        return 2, {"status": "blocked", "errors": [str(exc)]}
    if pre_registration.get("status") != "pre_registered":
        errors.append("S4 pre-registration is not frozen")
    if pre_registration.get("batch_id") != batch_id:
        errors.append("S4 pre-registration batch_id does not match requested batch")

    batch_root = store_root / batch_id
    try:
        reconciliation = load_json(batch_root / "reconciliation-report.json", "reconciliation report")
        ledger = load_json(batch_root / "intake-ledger.json", "intake ledger")
        gate = load_json(gate_path, "oracle gate")
        mutant_manifest = load_json(mutants_path, "mutant manifest")
    except ValueError as exc:
        errors.append(str(exc))
        reconciliation, ledger, gate, mutant_manifest = {}, {}, {}, {}

    if reconciliation.get("status") != "accepted":
        errors.append("promoted batch reconciliation is not accepted")
    if gate.get("status") != "accepted":
        errors.append("oracle/mutant gate is not accepted")
    if mutant_manifest.get("status") != "accepted":
        errors.append("mutant manifest is not accepted")

    suite_rows = accepted_suite_rows(ledger)
    if not suite_rows:
        errors.append("intake ledger has no accepted suite_author artifacts")
    targets = target_inventory(mutant_manifest, mutants_path)
    if len(targets) == 1:
        errors.append("mutant manifest has no accepted executable mutants")

    suites = []
    for row in suite_rows:
        run_id = row.get("run_id")
        suite_path = batch_root / "normalized" / run_id / "suite.py"
        manifest_path = batch_root / "normalized" / run_id / "suite_manifest.json"
        bridge = declared_bridge_contract(suite_path, manifest_path)
        suites.append({
            "run_id": run_id,
            "author_vendor": row.get("author_vendor"),
            "sample_index": row.get("sample_index"),
            "normalized_sha256": row.get("normalized_sha256"),
            "suite_path": str(suite_path),
            "bridge": bridge,
        })

    bridge_block = "no reviewed isolated no-egress S4 execution bridge is installed"
    errors.append(bridge_block)
    write_matrices(results_root, suite_rows, targets)
    output = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "blocked",
        "phase": "S4_suite_authoring",
        "batch_id": batch_id,
        "pre_registration_sha256": sha256(pre_registration_path),
        "inputs": {
            "store_root": str(store_root),
            "reconciliation_status": reconciliation.get("status"),
            "intake_status": {"accepted_suite_author": len(suite_rows), "total": ledger.get("total")},
            "oracle_gate_status": gate.get("status"),
            "mutant_manifest_status": mutant_manifest.get("status"),
        },
        "targets": targets,
        "suites": suites,
        "matrix_cell_status": "not_executed",
        "errors": list(dict.fromkeys(errors)),
    }
    (results_root / "s4-preflight.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    return 2, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    parser.add_argument("--results-root", type=Path, default=DEFAULT_RESULTS_ROOT)
    parser.add_argument("--gate-path", type=Path, default=DEFAULT_GATE)
    parser.add_argument("--mutants-path", type=Path, default=DEFAULT_MUTANTS)
    parser.add_argument("--pre-registration-path", type=Path, default=DEFAULT_PRE_REGISTRATION)
    args = parser.parse_args(argv)
    code, result = run_preflight(
        store_root=args.store_root, batch_id=args.batch_id, results_root=args.results_root,
        gate_path=args.gate_path, mutants_path=args.mutants_path,
        pre_registration_path=args.pre_registration_path,
    )
    print(json.dumps({"status": result["status"], "results_root": str(args.results_root), "errors": result["errors"]}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
