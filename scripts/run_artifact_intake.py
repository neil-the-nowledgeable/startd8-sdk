#!/usr/bin/env python3
"""Artifact Intake and Normalization Script (Step S2b / S5).

This script parses raw outputs from the reproduction database, extracts:
1. Javascript code blocks (Node.js test suites) for 'suite' experiments.
2. Protobuf and Markdown files for 'spec' experiments.
It normalizes them mechanically, saves them to disk, and records their status in the DB.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DB_PATH = REPO / ".startd8" / "bias_audit_reproduction.db"
SUITES_OUT_DIR = REPO / ".startd8" / "bias_audit" / "extracted_suites"
SPECS_OUT_DIR = REPO / ".startd8" / "bias_audit" / "extracted_specs"

def extract_js_code(raw_output: str) -> str | None:
    """Extract JavaScript code block from raw markdown output."""
    start_match = re.search(r"```(?:javascript|js)\n", raw_output, re.IGNORECASE)
    if not start_match:
        if "node:test" in raw_output and "node:assert" in raw_output:
            return raw_output.strip().strip("`").strip()
        return None
        
    start_idx = start_match.end()
    rest = raw_output[start_idx:]
    close_match = re.search(r"\n```\s*(?:\n|$)", rest)
    if close_match:
        end_idx = start_idx + close_match.start()
        return raw_output[start_idx:end_idx].strip()
    
    match = re.search(r"```(?:javascript|js)\n(.*?)```", raw_output, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
        
    return None

def extract_proto_code(raw_output: str) -> str | None:
    """Extract Proto code block from raw markdown output."""
    match = re.search(r"```(?:proto|protobuf)\n(.*?)```", raw_output, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None

def run_intake(db_path: Path, suites_dir: Path, specs_dir: Path):
    """Scan database for provisional raw outputs and process them."""
    if not db_path.exists():
        print(f"Database not found at {db_path}. Run reproduction harness first.", file=sys.stderr)
        sys.exit(1)

    suites_dir.mkdir(parents=True, exist_ok=True)
    specs_dir.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Find all runs with provisional artifacts
    cursor.execute("""
    SELECT a.run_id, a.artifact_id, a.file_path, r.raw_output, r.experiment_type
    FROM artifacts a
    JOIN runs r ON a.run_id = r.run_id
    WHERE a.status = 'provisional'
    """)
    
    provisional_runs = cursor.fetchall()
    
    if not provisional_runs:
        print("No provisional artifacts found to ingest.")
        conn.close()
        return

    print(f"Found {len(provisional_runs)} provisional artifact(s) to process.\n")
    
    accepted_count = 0
    rejected_count = 0
    
    for run_id, art_id, file_path, raw_output, exp_type in provisional_runs:
        print(f"Processing run: {run_id} (Type: {exp_type})")
        
        if exp_type == "suite":
            js_code = extract_js_code(raw_output)
            if js_code:
                js_code = js_code.strip() + "\n"
                content_hash = hashlib.sha256(js_code.encode("utf-8")).hexdigest()
                
                target_filename = f"{run_id}_suite.js"
                target_path = suites_dir / target_filename
                target_path.write_text(js_code, encoding="utf-8")
                print(f"  -> Extracted JS suite to: {target_path.relative_to(REPO)}")
                
                extracted_art_id = f"art-{run_id}-extracted-suite"
                cursor.execute("""
                INSERT OR REPLACE INTO artifacts (artifact_id, run_id, file_path, content_hash, content, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (extracted_art_id, run_id, str(target_path), content_hash, js_code, "accepted"))
                
                cursor.execute("UPDATE artifacts SET status = 'processed' WHERE artifact_id = ?", (art_id,))
                accepted_count += 1
            else:
                print("  -> REJECTED: Could not extract JavaScript code block.")
                cursor.execute("UPDATE artifacts SET status = 'rejected_with_reason' WHERE artifact_id = ?", (art_id,))
                rejected_count += 1

        elif exp_type == "spec":
            proto_code = extract_proto_code(raw_output)
            if proto_code:
                proto_code = proto_code.strip() + "\n"
                proto_hash = hashlib.sha256(proto_code.encode("utf-8")).hexdigest()
                
                # Write proto to disk
                proto_filename = f"{run_id}_pricing.proto"
                proto_path = specs_dir / proto_filename
                proto_path.write_text(proto_code, encoding="utf-8")
                print(f"  -> Extracted Proto contract to: {proto_path.relative_to(REPO)}")
                
                # Save proto to DB
                extracted_proto_id = f"art-{run_id}-extracted-proto"
                cursor.execute("""
                INSERT OR REPLACE INTO artifacts (artifact_id, run_id, file_path, content_hash, content, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (extracted_proto_id, run_id, str(proto_path), proto_hash, proto_code, "accepted"))
                
                # Write markdown requirements to disk
                reqs_filename = f"{run_id}_requirements.md"
                reqs_path = specs_dir / reqs_filename
                reqs_path.write_text(raw_output, encoding="utf-8")
                print(f"  -> Extracted Markdown spec to: {reqs_path.relative_to(REPO)}")
                
                # Save reqs to DB
                reqs_hash = hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
                extracted_reqs_id = f"art-{run_id}-extracted-requirements"
                cursor.execute("""
                INSERT OR REPLACE INTO artifacts (artifact_id, run_id, file_path, content_hash, content, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (extracted_reqs_id, run_id, str(reqs_path), reqs_hash, raw_output, "accepted"))
                
                cursor.execute("UPDATE artifacts SET status = 'processed' WHERE artifact_id = ?", (art_id,))
                accepted_count += 1
            else:
                print("  -> REJECTED: Could not extract Proto block.")
                cursor.execute("UPDATE artifacts SET status = 'rejected_with_reason' WHERE artifact_id = ?", (art_id,))
                rejected_count += 1
                
        print("-" * 50)
        
    conn.commit()
    conn.close()
    
    print(f"\nIntake process finished:")
    print(f"  Accepted & Extracted: {accepted_count}")
    print(f"  Rejected:             {rejected_count}")

if __name__ == "__main__":
    run_intake(DB_PATH, SUITES_OUT_DIR, SPECS_OUT_DIR)
