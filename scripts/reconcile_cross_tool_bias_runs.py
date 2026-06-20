#!/usr/bin/env python3
"""Reconcile an existing cross-tool authoring batch before audit-store promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from startd8.fde.redaction import redact


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = Path("/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1/raw")
DEFAULT_STORE_ROOT = REPO / ".startd8" / "bias-audit-store"
COMMON_FILES = {"metadata.json", "rendered_prompt.md", "stdout.log", "stderr.log"}
EXPERIMENT_FILES = {
    "suite_author": {"suite.py", "suite_manifest.json", "authoring_manifest.json", "self-manifest.schema.json"},
    "spec_author": {"spec.md", "authoring_manifest.json", "self-manifest.schema.json"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _scan(path: Path) -> list[str]:
    try:
        _, findings = redact(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ["unreadable"]
    return findings


def reconcile(raw_root: Path, schedule_path: Path) -> dict:
    schedule = _load(schedule_path)
    expected = {item["ordinal"]: item for item in schedule}
    seen, runs = set(), []
    for metadata_path in sorted(raw_root.glob("*/metadata.json")):
        run_dir, errors = metadata_path.parent, []
        try:
            metadata = _load(metadata_path)
        except (OSError, json.JSONDecodeError) as exc:
            metadata = {}
            errors.append(f"invalid_metadata:{type(exc).__name__}")
        ordinal, item = metadata.get("ordinal"), expected.get(metadata.get("ordinal"))
        if item is None:
            errors.append("unexpected_ordinal")
        else:
            seen.add(ordinal)
            for field in ("experiment", "tool_id", "author_vendor", "sample_index"):
                if metadata.get(field) != item[field]:
                    errors.append(f"schedule_mismatch:{field}")
        if metadata.get("status") != "success" or metadata.get("exit_code") != 0:
            errors.append("unsuccessful_run")
        if metadata.get("missing_files"):
            errors.append("reported_missing_files")
        required = COMMON_FILES | EXPERIMENT_FILES.get(metadata.get("experiment"), set())
        missing = sorted(name for name in required if not (run_dir / name).is_file())
        if missing:
            errors.append("missing_files:" + ",".join(missing))
        files, findings = [], []
        for path in sorted(run_dir.iterdir()):
            if path.is_file():
                files.append({"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size})
                findings.extend(_scan(path))
        if findings:
            errors.append("secret_scan:" + ",".join(sorted(set(findings))))
        runs.append({"ordinal": ordinal, "run_dir": run_dir.name, "metadata": metadata,
                     "files": files, "errors": errors, "status": "accepted" if not errors else "quarantined"})
    missing_ordinals = sorted(set(expected) - seen)
    return {
        "schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root), "schedule": str(schedule_path), "expected_runs": len(expected),
        "observed_runs": len(runs), "missing_ordinals": missing_ordinals, "runs": runs,
        "status": "accepted" if not missing_ordinals and all(run["status"] == "accepted" for run in runs) else "blocked",
    }


def promote(report: dict, raw_root: Path, store_root: Path, batch_id: str) -> Path:
    if report["status"] != "accepted":
        raise ValueError("cannot promote a blocked batch")
    batch_root = store_root / batch_id
    if batch_root.exists():
        raise ValueError(f"store batch already exists: {batch_root}")
    raw_destination = batch_root / "raw"
    raw_destination.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(raw_root, raw_destination)
    (batch_root / "reconciliation-report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with sqlite3.connect(batch_root / "audit.sqlite") as connection:
        connection.executescript("""
            CREATE TABLE authoring_runs (ordinal INTEGER PRIMARY KEY, run_dir TEXT, status TEXT, metadata_json TEXT);
            CREATE TABLE artifacts (ordinal INTEGER, path TEXT, sha256 TEXT, bytes INTEGER);
        """)
        for run in report["runs"]:
            connection.execute("INSERT INTO authoring_runs VALUES (?, ?, ?, ?)",
                               (run["ordinal"], run["run_dir"], run["status"], json.dumps(run["metadata"])))
            connection.executemany("INSERT INTO artifacts VALUES (?, ?, ?, ?)",
                                   [(run["ordinal"], f["path"], f["sha256"], f["bytes"]) for f in run["files"]])
    return batch_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--schedule", type=Path, default=None)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--batch-id", default="pricing-cross-tool-authoring-v1")
    parser.add_argument("--promote", action="store_true")
    args = parser.parse_args(argv)
    schedule = args.schedule or args.raw_root.parent / "authoring-schedule.json"
    report = reconcile(args.raw_root, schedule)
    report_path = args.raw_root.parent / "reconciliation-report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"reconciliation: {report['status']} ({report['observed_runs']}/{report['expected_runs']} runs)")
    if report["status"] != "accepted":
        print(f"report: {report_path}", file=sys.stderr)
        return 2
    if args.promote:
        print(f"promoted: {promote(report, args.raw_root, args.store_root, args.batch_id)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
