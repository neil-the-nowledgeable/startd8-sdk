#!/usr/bin/env python3
"""Review intake + mechanical normalization of bias-audit authoring artifacts (Phase 4).

Sources artifacts from the PROMOTED audit store (gated on an accepted reconciliation report — never
from an unaccepted temporary batch, S2c) and produces an accepted/rejected ledger plus a mechanically
normalized artifact set. Normalization is whitespace-only and self-guarded: any change that would
alter non-whitespace content is refused (rejected, not repaired). Every run records raw + normalized
checksums and the exact diff. Intake results live inside the store (the store manifest is
authoritative); raw evidence is read-only and never mutated.
"""
from __future__ import annotations

import argparse
import ast
import difflib
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STORE_ROOT = REPO / ".startd8" / "bias-audit-store"
DEFAULT_BATCH_ID = "pricing-cross-tool-authoring-v1"

# Structured rejection reason codes (guide Phase 4 req 3): stable, greppable, not free text.
REASON_RUN_FAILED = "run_failed"
REASON_MISSING_ARTIFACT = "missing_artifact"
REASON_MANIFEST_PARSE = "manifest_parse_error"
REASON_SCHEMA_INVALID = "schema_validation_failed"
REASON_SPEC_SECTIONS = "spec_sections_missing"
REASON_SUITE_SYNTAX = "suite_syntax_error"
REASON_FORBIDDEN_IMPORT = "forbidden_import"
REASON_NON_MECHANICAL = "non_mechanical_normalization_refused"

REQUIRED_SPEC_L2 = [
    "scope", "service behavior", "input/output shape",
    "validation behavior", "open item decisions", "assumptions", "non-goals",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def normalize_text(content: str) -> str:
    """Mechanical normalization ONLY: strip trailing whitespace per line, collapse to a single
    trailing newline. Idempotent. Introduces no semantic change."""
    return "\n".join(line.rstrip() for line in content.splitlines()).strip() + "\n"


def is_mechanical_only(raw: str, normalized: str) -> bool:
    """True iff raw->normalized differs only in whitespace — i.e. no token/character change beyond
    whitespace. Guards against any normalization that would alter expected values, rounding,
    ordering, or contract behavior (guide Phase 4 req 3)."""
    return "".join(raw.split()) == "".join(normalized.split())


def compute_diff(raw: str, normalized: str, name: str) -> str:
    """Unified diff raw->normalized, recorded for audit (guide Phase 4 req 2)."""
    return "".join(difflib.unified_diff(
        raw.splitlines(keepends=True), normalized.splitlines(keepends=True),
        fromfile=f"raw/{name}", tofile=f"normalized/{name}",
    ))


def check_spec_headers(content: str) -> list[str]:
    headers_l1, headers_l2 = [], []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("##"):
            headers_l2.append(line.lstrip("#").strip().lower())
        elif line.startswith("#"):
            headers_l1.append(line.lstrip("#").strip().lower())
    missing = [] if headers_l1 else ["title"]
    for r in REQUIRED_SPEC_L2:
        words = r.replace("/", " ").split()
        if not any(all(w in h for w in words) for h in headers_l2):
            missing.append(r)
    return missing


def check_suite_imports(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"SyntaxError: {e}"]
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name.split(".")[0] != "pytest" and name.name.split(".")[0] not in sys.stdlib_module_names:
                    forbidden.append(name.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] != "pytest" and node.module.split(".")[0] not in sys.stdlib_module_names:
                forbidden.append(node.module)
    return forbidden


def load_accepted_store(store_root: Path, batch_id: str) -> Path:
    """Return the promoted batch's raw root, REFUSING unless its reconciliation report is accepted
    (guide Phase 4 req 1: never accept artifacts from an unaccepted temporary batch)."""
    batch_root = store_root / batch_id
    report_path = batch_root / "reconciliation-report.json"
    if not report_path.is_file():
        raise SystemExit(f"intake blocked: no reconciliation report in promoted store: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "accepted":
        raise SystemExit(f"intake blocked: store batch not accepted (status={report.get('status')})")
    raw_root = batch_root / "raw"
    if not raw_root.is_dir():
        raise SystemExit(f"intake blocked: promoted store has no raw/ tree: {raw_root}")
    return raw_root


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS intake_runs (
            run_id TEXT PRIMARY KEY, ordinal INTEGER, experiment TEXT, tool_id TEXT,
            author_vendor TEXT, sample_index INTEGER, run_status TEXT
        );
        CREATE TABLE IF NOT EXISTS intake_results (
            run_id TEXT PRIMARY KEY, status TEXT, reason_code TEXT, detail TEXT,
            checked_at_utc TEXT, artifact TEXT,
            raw_sha256 TEXT, normalized_sha256 TEXT, diff TEXT,
            FOREIGN KEY (run_id) REFERENCES intake_runs(run_id)
        );
        CREATE TABLE IF NOT EXISTS intake_dispositions (
            rejected_run_id TEXT PRIMARY KEY,
            replacement_run_id TEXT,
            reason_code TEXT,
            reviewer TEXT,
            timestamp TEXT,
            FOREIGN KEY (rejected_run_id) REFERENCES intake_runs(run_id),
            FOREIGN KEY (replacement_run_id) REFERENCES intake_runs(run_id)
        );
    """)
    conn.commit()
    return conn


def evaluate_run(run_dir: Path, metadata: dict) -> tuple[str | None, str]:
    """Return (reason_code, detail). reason_code is None when the run is acceptable."""
    if metadata.get("status") != "success":
        return REASON_RUN_FAILED, f"exit_code={metadata.get('exit_code', -1)}"
    experiment = metadata["experiment"]
    manifest_file = run_dir / "authoring_manifest.json"
    schema_file = run_dir / "self-manifest.schema.json"
    spec_file, suite_file = run_dir / "spec.md", run_dir / "suite.py"
    suite_manifest_file = run_dir / "suite_manifest.json"

    if experiment == "spec_author":
        if not spec_file.is_file():
            return REASON_MISSING_ARTIFACT, "spec.md"
    else:
        if not suite_file.is_file():
            return REASON_MISSING_ARTIFACT, "suite.py"
        if not suite_manifest_file.is_file():
            return REASON_MISSING_ARTIFACT, "suite_manifest.json"
    if not manifest_file.is_file():
        return REASON_MISSING_ARTIFACT, "authoring_manifest.json"

    if schema_file.is_file():
        try:
            jsonschema.validate(
                instance=json.loads(manifest_file.read_text(encoding="utf-8")),
                schema=json.loads(schema_file.read_text(encoding="utf-8")),
            )
        except json.JSONDecodeError as e:
            return REASON_MANIFEST_PARSE, str(e)
        except jsonschema.ValidationError as e:
            return REASON_SCHEMA_INVALID, e.message

    if experiment == "spec_author":
        missing = check_spec_headers(spec_file.read_text(encoding="utf-8"))
        if missing:
            return REASON_SPEC_SECTIONS, ", ".join(missing)
    else:
        content = suite_file.read_text(encoding="utf-8")
        try:
            compile(content, "suite.py", "exec")
        except SyntaxError as e:
            return REASON_SUITE_SYNTAX, str(e)
        forbidden = check_suite_imports(content)
        if forbidden:
            return REASON_FORBIDDEN_IMPORT, ", ".join(forbidden)
    return None, ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    args = parser.parse_args(argv)

    raw_root = load_accepted_store(args.store_root, args.batch_id)  # gated on accepted report
    batch_root = args.store_root / args.batch_id
    normalized_dir = batch_root / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    conn = init_db(batch_root / "intake.sqlite")
    cur = conn.cursor()

    dispositions = []
    dispositions_file = batch_root / "dispositions.json"
    if dispositions_file.is_file():
        try:
            dispositions = json.loads(dispositions_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"Warning: failed to parse dispositions.json: {e}", file=sys.stderr)

    summary = []
    for run_dir in sorted(d for d in raw_root.iterdir() if d.is_dir()):
        metadata_file = run_dir / "metadata.json"
        if not metadata_file.is_file():
            continue
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        run_id, experiment = metadata["run_id"], metadata["experiment"]
        cur.execute("INSERT OR REPLACE INTO intake_runs VALUES (?,?,?,?,?,?,?)",
                    (run_id, metadata["ordinal"], experiment, metadata["tool_id"],
                     metadata["author_vendor"], metadata["sample_index"], metadata.get("status")))

        reason_code, detail = evaluate_run(run_dir, metadata)
        artifact = "spec.md" if experiment == "spec_author" else "suite.py"
        art_path = run_dir / artifact
        raw_text = art_path.read_text(encoding="utf-8") if art_path.is_file() else ""
        raw_sha = _sha256_bytes(raw_text.encode()) if raw_text else None
        norm_sha, diff = None, ""

        if reason_code is None:
            normalized = normalize_text(raw_text)
            if not is_mechanical_only(raw_text, normalized):
                # Refuse to repair — a normalization that touches non-whitespace is out of scope.
                reason_code, detail = REASON_NON_MECHANICAL, artifact
            else:
                diff = compute_diff(raw_text, normalized, artifact)
                norm_run = normalized_dir / run_dir.name
                norm_run.mkdir(parents=True, exist_ok=True)
                (norm_run / artifact).write_text(normalized, encoding="utf-8")
                norm_sha = _sha256(norm_run / artifact)
                for extra in ("authoring_manifest.json", "suite_manifest.json"):
                    if (run_dir / extra).is_file():
                        shutil.copy2(run_dir / extra, norm_run / extra)  # manifests copied verbatim
                if (run_dir / "inputs").is_dir():
                    shutil.copytree(run_dir / "inputs", norm_run / "inputs", dirs_exist_ok=True)

        status = "accepted" if reason_code is None else "rejected_with_reason"
        cur.execute("INSERT OR REPLACE INTO intake_results VALUES (?,?,?,?,?,?,?,?,?)",
                    (run_id, status, reason_code, detail,
                     datetime.now(timezone.utc).isoformat(), artifact, raw_sha, norm_sha, diff))
        summary.append({"run_id": run_id, "ordinal": metadata["ordinal"], "experiment": experiment,
                        "tool_id": metadata["tool_id"], "author_vendor": metadata["author_vendor"],
                        "status": status, "reason_code": reason_code, "detail": detail,
                        "raw_sha256": raw_sha, "normalized_sha256": norm_sha})
        print(f"{run_id}: {status}" + (f" ({reason_code}: {detail})" if reason_code else ""))

    if dispositions:
        cur.execute("DELETE FROM intake_dispositions")
        for disp in dispositions:
            cur.execute("INSERT OR REPLACE INTO intake_dispositions VALUES (?,?,?,?,?)",
                        (disp.get("rejected_run_id"), disp.get("replacement_run_id"),
                         disp.get("reason_code"), disp.get("reviewer"), disp.get("timestamp")))
    conn.commit()
    conn.close()
    accepted = sum(1 for s in summary if s["status"] == "accepted")
    ledger = {"schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "store_batch": str(batch_root), "raw_root": str(raw_root),
              "total": len(summary), "accepted": accepted, "rejected": len(summary) - accepted,
              "runs": summary}
    if dispositions:
        ledger["dispositions"] = dispositions
    (batch_root / "intake-ledger.json").write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    print(f"\nintake: {accepted}/{len(summary)} accepted -> {batch_root}/intake-ledger.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
