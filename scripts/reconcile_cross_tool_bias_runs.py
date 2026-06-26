#!/usr/bin/env python3
"""Reconcile an existing cross-tool authoring batch before audit-store promotion."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from startd8.fde.redaction import _PATTERNS, redact

# Audit-record redactor: mask every HIGH-CONFIDENCE secret pattern (api keys, bearer, generic
# secret assignments) but NOT `dotenv_line` itself — the allow-list record exists precisely to show
# the reviewer the benign lowercase identifier (e.g. `line_key = ...`) that dotenv_line over-matched.
# Any real secret literal on the same line is still masked.
_AUDIT_PATTERNS = [(desc, pat) for desc, pat in _PATTERNS if desc != "dotenv_line"]


def _redact_for_audit(text: str) -> str:
    for desc, pat in _AUDIT_PATTERNS:
        text = pat.sub(f"«REDACTED:{desc}»", text)
    return text


REPO = Path(__file__).resolve().parents[1]
DEFAULT_RAW_ROOT = Path("/private/tmp/startd8-cross-tool-bias/pricing-cross-tool-authoring-v1/raw")
DEFAULT_STORE_ROOT = REPO / ".startd8" / "bias-audit-store"
COMMON_FILES = {"metadata.json", "rendered_prompt.md", "stdout.log", "stderr.log"}
EXPERIMENT_FILES = {
    "suite_author": {"suite.py", "suite_manifest.json", "authoring_manifest.json", "self-manifest.schema.json"},
    "spec_author": {"spec.md", "authoring_manifest.json", "self-manifest.schema.json"},
}

# Reviewed scanner ruleset for batch reconciliation. Bump on any change to the allow-list logic so
# every reconciliation report records exactly which rules dispositioned its findings.
SCANNER_RULESET_VERSION = "reconcile-scan/2"
# Allow-list rationale (Phase 2 false-positive disposition): the shared prose-redaction `dotenv_line`
# rule (startd8.fde.redaction) is case-INSENSITIVE by design — correct for stripping secrets from
# free prose before LLM submission, where over-matching is safe. Applied to generated *Python source*
# during reconciliation it over-fires on ordinary lowercase identifiers (e.g. `line_key = ln.get(...)`,
# a pricing line-item key — no secret value present). A genuine dotenv secret line carries an ALL-CAPS
# environment name (`OPENAI_API_KEY=...`). We therefore re-verify every `dotenv_line` hit against a
# case-SENSITIVE pattern: a file whose dotenv_line hits are all lowercase identifiers (no strict match)
# is a reviewed false positive and the finding is dropped *with the redacted candidate lines recorded*;
# a strict ALL-CAPS match is preserved as a real finding (the batch stays quarantined). This narrows the
# false positive without weakening the shared prose path or real secret detection.
_DOTENV_FINDING_PREFIX = "dotenv_line"
_DOTENV_LENIENT = re.compile(r"(?im)^\s*[A-Z][A-Z0-9_]*_(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*\S+$")
_DOTENV_STRICT = re.compile(r"(?m)^[ \t]*[A-Z][A-Z0-9_]*_(?:KEY|TOKEN|SECRET|PASSWORD)[ \t]*=[ \t]*\S+$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _scanner_record() -> dict:
    return {
        "ruleset_version": SCANNER_RULESET_VERSION,
        "allowlist_rules": [{
            "rule": "dotenv_line_lowercase_identifier",
            "rationale": (
                "Shared prose-redaction dotenv_line rule is case-insensitive and over-fires on "
                "lowercase source identifiers; re-verified case-sensitively against ALL-CAPS env "
                "names. Lowercase-only hits (no strict match) are reviewed false positives."
            ),
        }],
        "total_allowlisted": 0,
    }


def _blocked_report(raw_root: Path, schedule_path: Path, errors: list[str]) -> dict:
    return {
        "schema_version": "1.1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root), "schedule": str(schedule_path), "expected_runs": 0,
        "observed_runs": 0, "missing_ordinals": [], "scanner": _scanner_record(),
        "runs": [], "status": "blocked", "preflight_errors": errors,
    }


def _scan(path: Path) -> tuple[list[str], list[dict]]:
    """Return (kept_findings, allowlisted). Real secret patterns pass through untouched; a
    `dotenv_line` hit that is only a lowercase source identifier (no case-sensitive ALL-CAPS match)
    is dropped as a reviewed false positive, with redacted candidate lines recorded for audit."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["unreadable"], []
    _, findings = redact(text)
    kept: list[str] = []
    allowlisted: list[dict] = []
    for finding in findings:
        if finding.startswith(_DOTENV_FINDING_PREFIX) and not _DOTENV_STRICT.search(text):
            # Reviewed false positive: lowercase identifier(s) only. Record redacted evidence.
            for match in _DOTENV_LENIENT.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                safe_line = _redact_for_audit(match.group(0).strip())
                allowlisted.append({
                    "file": path.name, "line": line_no, "redacted": safe_line,
                    "rule": "dotenv_line_lowercase_identifier", "ruleset": SCANNER_RULESET_VERSION,
                })
        else:
            kept.append(finding)
    return kept, allowlisted


def reconcile(raw_root: Path, schedule_path: Path) -> dict:
    preflight_errors: list[str] = []
    try:
        schedule = _load(schedule_path)
    except FileNotFoundError:
        preflight_errors.append(f"missing_schedule:{schedule_path}")
        schedule = []
    except (OSError, json.JSONDecodeError) as exc:
        preflight_errors.append(f"invalid_schedule:{type(exc).__name__}:{schedule_path}")
        schedule = []
    if not isinstance(schedule, list):
        preflight_errors.append(f"invalid_schedule:not_list:{schedule_path}")
        schedule = []
    if not raw_root.is_dir():
        preflight_errors.append(f"missing_raw_root:{raw_root}")
    if preflight_errors:
        return _blocked_report(raw_root, schedule_path, preflight_errors)

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
        files, findings, allowlisted = [], [], []
        for path in sorted(run_dir.iterdir()):
            if path.is_file():
                files.append({"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size})
                kept, dropped = _scan(path)
                findings.extend(kept)
                allowlisted.extend(dropped)
        if findings:
            errors.append("secret_scan:" + ",".join(sorted(set(findings))))
        run_record = {"ordinal": ordinal, "run_dir": run_dir.name, "metadata": metadata,
                      "files": files, "errors": errors,
                      "status": "accepted" if not errors else "quarantined"}
        if allowlisted:
            run_record["allowlisted_findings"] = allowlisted
        runs.append(run_record)
    missing_ordinals = sorted(set(expected) - seen)
    return {
        "schema_version": "1.1", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_root": str(raw_root), "schedule": str(schedule_path), "expected_runs": len(expected),
        "observed_runs": len(runs), "missing_ordinals": missing_ordinals,
        "scanner": {**_scanner_record(),
                    "total_allowlisted": sum(len(r.get("allowlisted_findings", [])) for r in runs)},
        "runs": runs,
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
    # Exclude non-evidence execution byproducts. The generated suites were run for validation, which
    # leaves `__pycache__`/`*.pyc`/`.pytest_cache` inside each run dir; these are not captured evidence
    # (the reconciliation checksums cover only top-level artifacts) and must not enter the immutable
    # store. (That suites were executed in-place in the raw tree is an isolation defect tracked for
    # controller hardening — generated code should run in an isolated workspace, not the evidence dir.)
    shutil.copytree(raw_root, raw_destination,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
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
