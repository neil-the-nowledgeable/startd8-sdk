#!/usr/bin/env python3
"""Runner for S4: Experiment A (Suite-Author Bias).

Runs the extracted model-generated Node.js test suites against the reference
oracle and each mutant server, parses their pass/fail output, and generates
the mutant kill matrix and suite equivalence metrics.
"""

import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB_MANIFEST = REPO / ".startd8" / "bias_audit" / "mutants" / "mutant_manifest.json"
SUITES_DIR = REPO / ".startd8" / "bias_audit" / "extracted_suites"
OUT_RESULTS = REPO / ".startd8" / "bias_audit" / "experiment_a_results.json"

ORACLE_JS = REPO / ".startd8" / "bias_audit" / "oracle" / "reference_server.js"
MUTANTS_DIR = REPO / ".startd8" / "bias_audit" / "mutants"

def get_free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

def run_server(js_path: Path, port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["NODE_PATH"] = str(REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime" / "node_modules")
    
    proc = subprocess.Popen(
        ["node", str(js_path)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(js_path.parent),
        preexec_fn=os.setsid if hasattr(os, "setsid") else None
    )
    time.sleep(0.5)
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

def execute_suite(suite_path: Path, port: int, proto_path: Path) -> dict:
    """Run a JS test suite against a running server port using node --test."""
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["SERVER_ADDRESS"] = f"127.0.0.1:{port}"
    env["PROTO_PATH"] = str(proto_path)
    env["NODE_PATH"] = str(REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime" / "node_modules")
    
    # Run node with --test
    proc = subprocess.run(
        ["node", "--test", str(suite_path)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(suite_path.parent),
        text=True
    )
    
    # Parse the output for passed and failed tests
    passed_tests = []
    failed_tests = []
    crashed = False
    error_msg = ""

    lines = proc.stdout.splitlines()
    for line in lines:
        line_strip = line.strip()
        # Node test runner output matches:
        # ✔ [test name] -> passed
        # ✖ [test name] -> failed/cancelled
        if line_strip.startswith("✔"):
            test_name = line_strip[1:].strip()
            passed_tests.append(test_name)
        elif line_strip.startswith("✖"):
            test_name = line_strip[1:].strip()
            # Avoid duplicating parent suite names as failed tests
            if not any(test_name.endswith(s) for s in ["API", "Logic", "Strategies", "Ordering", "Precision", "Validation", "Aggregation"]):
                failed_tests.append(test_name)

    # Check for compile errors / crashes
    if not passed_tests and not failed_tests:
        crashed = True
        error_msg = proc.stderr.strip() or proc.stdout.strip()
        if not error_msg:
            error_msg = "Unknown crash / no tests executed"

    return {
        "passed": passed_tests,
        "failed": failed_tests,
        "crashed": crashed,
        "error": error_msg,
        "exit_code": proc.returncode
    }

def calculate_jaccard_distance(v1: list, v2: list) -> float:
    """Calculate Jaccard distance between two boolean vectors of identical size."""
    if len(v1) != len(v2) or not v1:
        return 1.0
    intersection = sum(1 for a, b in zip(v1, v2) if a and b)
    union = sum(1 for a, b in zip(v1, v2) if a or b)
    if union == 0:
        return 0.0
    return 1.0 - (intersection / union)

def main():
    print("=" * 80)
    print("S4: Experiment A (Suite-Author Bias) Runner")
    print("=" * 80)

    if not DB_MANIFEST.exists():
        print(f"ERROR: S3 mutant manifest not found at {DB_MANIFEST}. Run S3 first.", file=sys.stderr)
        return 1

    with open(DB_MANIFEST, "r", encoding="utf-8") as f:
        manifest_s3 = json.load(f)

    suite_files = sorted(SUITES_DIR.glob("*_suite.js"))
    if not suite_files:
        print(f"ERROR: No extracted suites found in {SUITES_DIR}. Run S2b first.", file=sys.stderr)
        return 1

    print(f"Found {len(suite_files)} suite file(s).")
    for s in suite_files:
        print(f"  - {s.name}")

    # Build the list of targets to run against: Oracle + Mutants
    targets = [
        {"name": "oracle", "path": ORACLE_JS, "proto": ORACLE_JS.parent / "pricing.proto"}
    ]
    for mutant_name, data in manifest_s3["mutants"].items():
        targets.append({
            "name": mutant_name,
            "path": REPO / data["file"],
            "proto": REPO / data["file"].replace(f"{mutant_name}.js", "pricing.proto")
        })

    results = {}

    for target in targets:
        target_name = target["name"]
        print(f"\nRunning suites against target: {target_name}...")
        results[target_name] = {}
        
        # Start server
        port = get_free_port()
        proc = run_server(target["path"], port)
        
        try:
            for sf in suite_files:
                suite_name = sf.name
                outcome = execute_suite(sf, port, target["proto"])
                
                results[target_name][suite_name] = {
                    "passed_count": len(outcome["passed"]),
                    "failed_count": len(outcome["failed"]),
                    "crashed": outcome["crashed"],
                    "error": outcome["error"][:300] if outcome["error"] else "",
                    "total_assertions": len(outcome["passed"]) + len(outcome["failed"])
                }
                
                status_str = "CRASHED" if outcome["crashed"] else f"{len(outcome['passed'])}/{len(outcome['passed'])+len(outcome['failed'])} passed"
                print(f"  Suite '{suite_name}': {status_str}")
        finally:
            kill_server(proc)

    # Compute equivalence matrices
    # Jaccard distance between suites based on their pass/fail outcome vector across all targets.
    # A suite's outcome vector is 1 for pass, 0 for fail/crash.
    suite_vectors = {}
    for sf in suite_files:
        suite_name = sf.name
        vector = []
        for target in targets:
            target_name = target["name"]
            res = results[target_name][suite_name]
            # Vector is the count of passed assertions (or binary whether it crashed/failed)
            # To be precise, let's use the fraction of passed tests as a continuous vector element
            total = res["total_assertions"]
            fraction = res["passed_count"] / total if total > 0 else 0.0
            vector.append(fraction)
        suite_vectors[suite_name] = vector

    jaccard_matrix = {}
    for sf1 in suite_files:
        jaccard_matrix[sf1.name] = {}
        for sf2 in suite_files:
            # Binarize vector for Jaccard: passed all tests = 1, otherwise = 0
            v1_bin = [1 if val == 1.0 else 0 for val in suite_vectors[sf1.name]]
            v2_bin = [1 if val == 1.0 else 0 for val in suite_vectors[sf2.name]]
            jaccard_matrix[sf1.name][sf2.name] = calculate_jaccard_distance(v1_bin, v2_bin)

    output_data = {
        "runs": results,
        "vectors": suite_vectors,
        "jaccard_equivalence_matrix": jaccard_matrix
    }

    with open(OUT_RESULTS, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"\nSUCCESS: Experiment A results written to: {OUT_RESULTS.relative_to(REPO)}")

    # Summary table
    print("\n" + "=" * 90)
    print(f"{'Target Server':<30} | " + " | ".join(f"{sf.name[:25]:<25}" for sf in suite_files))
    print("-" * 90)
    for target in targets:
        target_name = target["name"]
        row_str = f"{target_name:<30}"
        for sf in suite_files:
            res = results[target_name][sf.name]
            if res["crashed"]:
                outcome_str = "CRASHED"
            else:
                outcome_str = f"{res['passed_count']}/{res['total_assertions']}"
            row_str += f" | {outcome_str:<25}"
        print(row_str)
    print("=" * 90)

    return 0

if __name__ == "__main__":
    main()
