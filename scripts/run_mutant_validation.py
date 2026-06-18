#!/usr/bin/env python3
"""Validation runner for S3 Oracle & Mutant Battery.

Starts the reference Node server and each mutant server, runs the behavioral
pricing suite against it, and records the expected-kill matrix to a manifest.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from startd8.benchmark_matrix.behavioral.pricing_suite import run_pricing_suite

ORACLE_JS = REPO / ".startd8" / "bias_audit" / "oracle" / "reference_server.js"
MUTANTS_DIR = REPO / ".startd8" / "bias_audit" / "mutants"
MANIFEST_PATH = MUTANTS_DIR / "mutant_manifest.json"

def get_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def run_server(js_path: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["PORT"] = str(port)
    # Point NODE_PATH to the vendored node_modules closure
    env["NODE_PATH"] = str(REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime" / "node_modules")
    
    proc = subprocess.Popen(
        ["node", str(js_path)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(js_path.parent),
        preexec_fn=os.setsid if hasattr(os, "setsid") else None
    )
    
    # Wait briefly for startup
    time.sleep(0.5)
    
    # Check if process died immediately
    if proc.poll() is not None:
        stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"Server failed to start immediately: {js_path.name}\n"
            f"stdout: {stdout.decode()}\n"
            f"stderr: {stderr.decode()}"
        )
    return proc

def kill_server(proc: subprocess.Popen):
    try:
        if hasattr(os, "killpg"):
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=2)
    except Exception:
        proc.kill()
        proc.wait()

def run_suite_against_js(js_path: Path) -> dict:
    port = get_free_port()
    proc = run_server(js_path, port)
    
    try:
        result = run_pricing_suite(port, host="127.0.0.1", connect_timeout=3.0)
        if result.connect_error:
            # Check stderr for diagnostic info
            proc.terminate()
            stdout, stderr = proc.communicate()
            raise RuntimeError(
                f"Failed to connect to server {js_path.name} on port {port}: {result.connect_error}\n"
                f"stderr tail:\n{stderr.decode()[-500:]}"
            )
        return result.to_dict()
    finally:
        kill_server(proc)

def main():
    print("=" * 80)
    print("S3: Oracle & Mutant Battery Validation Runner")
    print("=" * 80)

    # 1. Test Oracle
    print(f"\nEvaluating Reference Oracle: {ORACLE_JS.name}...")
    try:
        oracle_outcome = run_suite_against_js(ORACLE_JS)
    except Exception as e:
        print(f"ERROR: Oracle failed to execute: {e}", file=sys.stderr)
        return 1

    oracle_coverage = oracle_outcome["coverage"]
    print(f"Oracle Coverage: {oracle_coverage * 100:.1f}% ({sum(1 for r in oracle_outcome['results'] if r['passed'])}/{len(oracle_outcome['results'])} passed)")
    
    failing_oracle = [r for r in oracle_outcome["results"] if not r["passed"]]
    if failing_oracle:
        print("FATAL: Reference Oracle has failing test cases:", file=sys.stderr)
        for r in failing_oracle:
            print(f"  - {r['name']}: {r['detail']}", file=sys.stderr)
        return 1
    
    print("SUCCESS: Reference Oracle passed all assertions!")

    # 2. Test Mutants
    mutant_files = sorted(MUTANTS_DIR.glob("mutant_*.js"))
    if not mutant_files:
        print("ERROR: No mutants found in mutants/ directory.", file=sys.stderr)
        return 1

    print(f"\nEvaluating {len(mutant_files)} Mutants...")
    manifest = {
        "oracle": {
            "file": str(ORACLE_JS.relative_to(REPO)),
            "status": "passed",
            "total_assertions": len(oracle_outcome["results"])
        },
        "mutants": {}
    }

    kill_matrix = {}
    
    for mf in mutant_files:
        name = mf.stem
        print(f"  Testing mutant '{name}'...")
        try:
            mutant_outcome = run_suite_against_js(mf)
        except Exception as e:
            print(f"  ERROR: Mutant {name} crashed or failed to run: {e}", file=sys.stderr)
            return 1
        
        killed_by = [r["name"] for r in mutant_outcome["results"] if not r["passed"]]
        passed_count = sum(1 for r in mutant_outcome["results"] if r["passed"])
        total_count = len(mutant_outcome["results"])
        
        if not killed_by:
            print(f"  WARNING: Mutant '{name}' was NOT killed by any test (functional={passed_count}/{total_count})!", file=sys.stderr)
        else:
            print(f"    -> KILLED by {len(killed_by)} test(s): {', '.join(killed_by)}")
        
        manifest["mutants"][name] = {
            "file": str(mf.relative_to(REPO)),
            "killed": len(killed_by) > 0,
            "killed_by": killed_by,
            "assertions_passed": passed_count,
            "total_assertions": total_count
        }

    # Verify mutant adequacy criteria (at least 1 mutant per OPEN/FIXED dimension is killed)
    unkilled = [m for m, data in manifest["mutants"].items() if not data["killed"]]
    if unkilled:
        print(f"\nFATAL: The following mutants were not killed: {unkilled}", file=sys.stderr)
        return 1

    # Write manifest
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nSUCCESS: Mutant manifest written to: {MANIFEST_PATH.relative_to(REPO)}")
    
    # Print a summary table
    print("\n" + "=" * 80)
    print(f"{'Mutant Name':<30} | {'Status':<10} | {'Killed By (Primary Test Case)':<35}")
    print("-" * 80)
    for name, data in manifest["mutants"].items():
        status = "KILLED" if data["killed"] else "SURVIVED"
        killer = data["killed_by"][0] if data["killed_by"] else "N/A"
        print(f"{name:<30} | {status:<10} | {killer:<35}")
    print("=" * 80)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
