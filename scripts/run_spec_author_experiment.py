#!/usr/bin/env python3
"""Runner for S5: Experiment B (Spec-Author Bias).

For each model-generated spec variant, swaps its requirements into the seed
configuration, runs the flagship benchmark evaluation for gemini-2.5-pro,
and captures the resulting functional coverage score.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED_JSON = REPO / "docs" / "design" / "model-benchmark" / "seeds" / "seed-pricingservice.json"
SPECS_DIR = REPO / ".startd8" / "bias_audit" / "extracted_specs"
OUT_RESULTS = REPO / ".startd8" / "bias_audit" / "experiment_b_results.json"

def main():
    print("=" * 80)
    print("S5: Experiment B (Spec-Author Bias) Runner")
    print("=" * 80)

    # Find the accepted spec requirements files
    spec_reqs = sorted(SPECS_DIR.glob("*_requirements.md"))
    if not spec_reqs:
        print(f"ERROR: No extracted spec requirements found in {SPECS_DIR}. Run S2b/intake first.", file=sys.stderr)
        return 1

    print(f"Found {len(spec_reqs)} spec requirements file(s).")
    for r in spec_reqs:
        print(f"  - {r.name}")

    if not SEED_JSON.exists():
        print(f"ERROR: Seed config file not found at {SEED_JSON}", file=sys.stderr)
        return 1

    # Load original seed JSON as backup
    original_seed_content = SEED_JSON.read_text(encoding="utf-8")
    original_seed = json.loads(original_seed_content)

    results = {}

    for sf in spec_reqs:
        run_id = sf.name.replace("_requirements.md", "")
        print(f"\nEvaluating spec variant: {run_id}...")
        
        # Read the generated spec requirements
        spec_text = sf.read_text(encoding="utf-8")
        
        # Update the seed JSON requirements_text
        modified_seed = original_seed.copy()
        modified_seed["tasks"][0]["config"]["requirements_text"] = spec_text
        
        # Write modified seed to docs/design/model-benchmark/seeds/seed-pricingservice.json
        SEED_JSON.write_text(json.dumps(modified_seed, indent=2), encoding="utf-8")
        
        # Output directory for this evaluation run
        eval_out_dir = REPO / ".startd8" / "bias_audit" / "benchmark-runs" / run_id
        if eval_out_dir.exists():
            shutil.rmtree(eval_out_dir)
        eval_out_dir.mkdir(parents=True, exist_ok=True)

        
        # Run flagship benchmark under Doppler for 1 repetition on gemini:gemini-2.5-pro
        cmd = [
            "doppler", "run", "-p", "startd8", "-c", "dev", "--",
            ".venv/bin/python3", "scripts/run_flagship_benchmark.py",
            "--run",
            "--budget", "5.0",
            "--services", "pricingservice",
            "--reps", "1",
            "--models", "gemini:gemini-2.5-pro",
            "--out-dir", str(eval_out_dir)
        ]
        
        print(f"  Running flagship benchmark...")
        proc = subprocess.run(cmd, cwd=str(REPO), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if proc.returncode != 0:
            print(f"  ERROR: Benchmark run failed for {run_id} (exit code: {proc.returncode})", file=sys.stderr)
            print(proc.stderr, file=sys.stderr)
            results[run_id] = {
                "status": "failed",
                "error": proc.stderr[-500:] if proc.stderr else "Unknown error"
            }
            continue
            
        # Parse the cells.json file to extract the score
        cells_path = eval_out_dir / "cells.json"
        if not cells_path.exists():
            print(f"  ERROR: cells.json not found at {cells_path}", file=sys.stderr)
            results[run_id] = {
                "status": "failed",
                "error": "cells.json missing"
            }
            continue
            
        with open(cells_path, "r") as f:
            cells = json.load(f)
            
        if not cells:
            print("  ERROR: cells.json is empty", file=sys.stderr)
            results[run_id] = {
                "status": "failed",
                "error": "cells.json empty"
            }
            continue
            
        cell = cells[0]
        score = cell.get("functional_coverage")
        status = cell.get("status")
        quality = cell.get("quality")
        
        print(f"  Result: status={status}, functional_coverage={score}, quality={quality}")
        results[run_id] = {
            "status": status,
            "functional_coverage": score,
            "quality": quality,
            "error_msg": cell.get("error_msg", "")
        }

    # Restore original seed JSON
    SEED_JSON.write_text(original_seed_content, encoding="utf-8")
    print("\nRestored original seed JSON configuration.")

    # Write experiment B results
    with open(OUT_RESULTS, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"SUCCESS: Experiment B results written to: {OUT_RESULTS.relative_to(REPO)}")

    # Summary table
    print("\n" + "=" * 80)
    print(f"{'Spec Run ID':<45} | {'Status':<10} | {'Score':<10} | {'Quality':<10}")
    print("-" * 80)
    for run_id, data in results.items():
        score_val = f"{data.get('functional_coverage'):.2f}" if data.get("functional_coverage") is not None else "N/A"
        qual_val = f"{data.get('quality'):.2f}" if data.get("quality") is not None else "N/A"
        print(f"{run_id:<45} | {data['status']:<10} | {score_val:<10} | {qual_val:<10}")
    print("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())
