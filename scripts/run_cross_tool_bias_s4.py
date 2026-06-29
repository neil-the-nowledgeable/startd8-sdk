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
import os
import shutil
import subprocess
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
DEFAULT_BRIDGE_MANIFEST = AUDIT_ROOT / "analysis/s4-bridge-manifest.json"

SECRET_ENV_MARKERS = (
    "API_KEY", "_TOKEN", "TOKEN_", "_SECRET", "SECRET_", "PASSWORD",
    "ANTHROPIC", "OPENAI", "GOOGLE", "GEMINI", "MISTRAL", "NVIDIA",
    "AWS_", "DOPPLER", "_KEY", "CREDENTIAL",
)
SAFE_ENV_KEYS = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "SystemRoot")


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


def scrub_bridge_env(workspace: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    source = dict(os.environ if base is None else base)
    clean = {
        key: value for key, value in source.items()
        if key in SAFE_ENV_KEYS and not any(marker in key.upper() for marker in SECRET_ENV_MARKERS)
    }
    clean["HOME"] = str(workspace)
    clean["TMPDIR"] = str(workspace)
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    clean["PYTHONUNBUFFERED"] = "1"
    return clean


def bridge_caps() -> dict[str, bool]:
    return {
        "sandbox_exec": sys.platform == "darwin" and shutil.which("sandbox-exec") is not None,
        "unshare": sys.platform.startswith("linux") and shutil.which("unshare") is not None,
    }


def wrap_no_egress_command(cmd: list[str], caps: dict[str, bool]) -> tuple[list[str], str | None]:
    if caps.get("sandbox_exec"):
        profile = "(version 1)(allow default)(deny network*)"
        return ["sandbox-exec", "-p", profile, *cmd], "seatbelt-no-egress"
    if caps.get("unshare"):
        return ["unshare", "-rn", *cmd], "linux-netns-no-egress"
    return cmd, None


def bridge_dry_run_gate(
    bridge_manifest_path: Path, results_root: Path, *,
    caps: dict[str, bool] | None = None,
    runner=subprocess.run,
) -> tuple[dict, list[str]]:
    """Validate reviewed S4 bridge prerequisites without importing or running generated suites."""
    errors: list[str] = []
    if not bridge_manifest_path.is_file():
        return {
            "status": "not_installed",
            "manifest_path": str(bridge_manifest_path),
            "dry_run": "not_run",
        }, [f"reviewed S4 bridge manifest is not installed:{bridge_manifest_path}"]

    try:
        manifest = load_json(bridge_manifest_path, "S4 bridge manifest")
    except ValueError as exc:
        return {
            "status": "invalid_manifest",
            "manifest_path": str(bridge_manifest_path),
            "dry_run": "not_run",
        }, [str(exc)]

    if manifest.get("status") != "reviewed":
        errors.append("reviewed S4 bridge manifest status is not reviewed")
    if manifest.get("require_no_egress") is not True:
        errors.append("reviewed S4 bridge manifest does not require no-egress isolation")
    if manifest.get("require_scrubbed_env") is not True:
        errors.append("reviewed S4 bridge manifest does not require scrubbed environment")
    if manifest.get("require_identical_inventory") is not True:
        errors.append("reviewed S4 bridge manifest does not require identical target inventory")

    caps = bridge_caps() if caps is None else caps
    dry_workspace = results_root / "bridge-dry-run-workspace"
    dry_workspace.mkdir(parents=True, exist_ok=True)
    command, isolation = wrap_no_egress_command(
        [sys.executable, "-c", "print('s4-bridge-dry-run-ok')"], caps
    )
    if isolation is None:
        errors.append("no real no-egress isolation capability available for S4 bridge dry-run")

    timeout_s = float(manifest.get("timeout_seconds", 10))
    max_output = int(manifest.get("max_output_bytes", 4096))
    dry_run = {
        "workspace": str(dry_workspace),
        "isolation": isolation,
        "timeout_seconds": timeout_s,
        "max_output_bytes": max_output,
    }
    if isolation is not None and not errors:
        try:
            proc = runner(
                command,
                cwd=str(dry_workspace),
                env=scrub_bridge_env(dry_workspace),
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
            dry_run.update({
                "returncode": proc.returncode,
                "stdout_tail": (proc.stdout or "")[-max_output:],
                "stderr_tail": (proc.stderr or "")[-max_output:],
            })
            if proc.returncode != 0:
                errors.append(f"S4 bridge dry-run failed:{proc.returncode}")
        except subprocess.TimeoutExpired:
            dry_run["timed_out"] = True
            errors.append(f"S4 bridge dry-run timed out after {timeout_s}s")

    return {
        "status": "ready" if not errors else "blocked",
        "manifest_path": str(bridge_manifest_path),
        "manifest_sha256": sha256(bridge_manifest_path),
        "capabilities": caps,
        "dry_run": dry_run,
    }, errors


def accepted_suite_rows(ledger: dict) -> list[dict]:
    return [
        row
        for row in ledger.get("runs", [])
        if row.get("status") == "accepted" and row.get("experiment") == "suite_author"
    ]


def suite_author_rows(ledger: dict) -> list[dict]:
    return [row for row in ledger.get("runs", []) if row.get("experiment") == "suite_author"]


def normalized_suite_record(batch_root: Path, row: dict, run_dir: str) -> tuple[dict, list[str]]:
    """Validate the promoted normalized suite artifact before any bridge inspection.

    S4 must consume exactly the artifact admitted by intake. Missing files, missing hashes, or
    checksum drift are input-gate failures, not bridge failures and never execution evidence.
    """
    errors: list[str] = []
    run_id = row.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        return {
            "run_id": run_id,
            "status": "invalid_intake",
            "detail": "accepted suite_author row has no run_id",
        }, ["intake accepted suite_author row has no run_id"]

    suite_path = batch_root / "normalized" / run_dir / "suite.py"
    manifest_path = batch_root / "normalized" / run_dir / "suite_manifest.json"
    expected_sha = row.get("normalized_sha256")
    actual_sha = sha256(suite_path) if suite_path.is_file() else None

    if not suite_path.is_file():
        errors.append(f"accepted suite_author missing normalized suite.py:{run_id}")
    if not manifest_path.is_file():
        errors.append(f"accepted suite_author missing normalized suite_manifest.json:{run_id}")
    if not isinstance(expected_sha, str) or not expected_sha:
        errors.append(f"accepted suite_author missing normalized_sha256:{run_id}")
    elif actual_sha is not None and actual_sha != expected_sha:
        errors.append(f"accepted suite_author normalized_sha256 mismatch:{run_id}")

    record = {
        "run_id": run_id,
        "author_vendor": row.get("author_vendor"),
        "sample_index": row.get("sample_index"),
        "normalized_sha256": expected_sha,
        "normalized_sha256_actual": actual_sha,
        "suite_path": str(suite_path),
        "manifest_path": str(manifest_path),
        "intake_status": row.get("status"),
    }
    return record, errors


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
    mutants_path: Path, pre_registration_path: Path, bridge_manifest_path: Path = DEFAULT_BRIDGE_MANIFEST,
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

    # Build a lookup from run_id to run_dir name from the reconciliation report
    run_dir_by_id = {}
    for run in reconciliation.get("runs", []):
        r_id = run.get("metadata", {}).get("run_id")
        r_dir = run.get("run_dir")
        if r_id and r_dir:
            run_dir_by_id[r_id] = r_dir

    dispositions = ledger.get("dispositions", [])
    replaced_run_ids = {d["rejected_run_id"] for d in dispositions}

    all_suite_rows = suite_author_rows(ledger)
    rejected_suite_rows = [
        row for row in all_suite_rows
        if row.get("status") != "accepted" and row.get("run_id") not in replaced_run_ids
    ]
    if rejected_suite_rows:
        errors.append(f"intake ledger has rejected suite_author artifacts:{len(rejected_suite_rows)}")

    suite_rows = accepted_suite_rows(ledger)
    if not suite_rows:
        errors.append("intake ledger has no accepted suite_author artifacts")
    targets = target_inventory(mutant_manifest, mutants_path)
    if len(targets) == 1:
        errors.append("mutant manifest has no accepted executable mutants")

    suites = []
    for row in suite_rows:
        run_id = row.get("run_id")
        run_dir = run_dir_by_id.get(run_id, run_id) # Fallback to run_id if missing
        suite_record, suite_errors = normalized_suite_record(batch_root, row, run_dir)
        errors.extend(suite_errors)
        if suite_errors:
            suite_record["bridge"] = {
                "status": "invalid_intake",
                "detail": "normalized suite artifact failed S4 intake invariants",
            }
        else:
            suite_record["bridge"] = declared_bridge_contract(
                Path(suite_record["suite_path"]), Path(suite_record["manifest_path"])
            )
        suites.append(suite_record)

    bridge, bridge_errors = bridge_dry_run_gate(bridge_manifest_path, results_root)
    errors.extend(bridge_errors)
    errors.append("S4 bridge execution remains disabled until the reviewed executor consumes the dry-run gate")
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
        "bridge": bridge,
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
    parser.add_argument("--bridge-manifest-path", type=Path, default=DEFAULT_BRIDGE_MANIFEST)
    args = parser.parse_args(argv)
    code, result = run_preflight(
        store_root=args.store_root, batch_id=args.batch_id, results_root=args.results_root,
        gate_path=args.gate_path, mutants_path=args.mutants_path,
        pre_registration_path=args.pre_registration_path, bridge_manifest_path=args.bridge_manifest_path,
    )
    print(json.dumps({"status": result["status"], "results_root": str(args.results_root), "errors": result["errors"]}, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
