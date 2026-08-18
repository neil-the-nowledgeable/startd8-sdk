#!/usr/bin/env python3
"""crp_lint — the det-crp/0.1 conformance lint CLI (SCHEMA_det-crp-0.1 §10).

Lints det-crp artifacts (CRP focus files + Appendix-A/B/C review-logs embedded in REQ/PLAN docs) for
review-log integrity — the cross-model memory must not silently lose a finding. Dogfood: run it over
the requirements-visualization corpus to lint our OWN CRP review-logs.

    python3 scripts/crp_lint.py                 # scan the default corpus dir
    python3 scripts/crp_lint.py <file>...       # lint specific files
    python3 scripts/crp_lint.py --dir <dir> [--json]

Exit 0 = clean (only warnings allowed with --warn-ok), 1 = an error-severity finding.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from startd8.crp_lint import (  # noqa: E402
    findings_to_sarif,
    has_focus,
    has_review_log,
    lint_crp,
)

DEFAULT_DIR = "docs/design/requirements-visualization"


def _targets(args: argparse.Namespace) -> List[Path]:
    if args.paths:
        return [Path(p) for p in args.paths]
    base = Path(args.dir)
    # A det-crp artifact = a focus file OR a doc carrying an Appendix-C review-log.
    return sorted(p for p in base.rglob("*.md") if _is_crp_artifact(p))


def _is_crp_artifact(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return has_focus(text) or has_review_log(text)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Lint det-crp/0.1 artifacts (review-log integrity)."
    )
    ap.add_argument(
        "paths", nargs="*", help="Specific files to lint (default: scan --dir)."
    )
    ap.add_argument(
        "--dir", default=DEFAULT_DIR, help="Corpus dir to scan for det-crp artifacts."
    )
    ap.add_argument(
        "--sarif",
        type=Path,
        help="Also write all findings as SARIF 2.1.0 to this path.",
    )
    ap.add_argument("--json", action="store_true", help="Emit the report as JSON.")
    args = ap.parse_args(argv)

    targets = _targets(args)
    all_findings = []
    per_file = []
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            per_file.append({"file": str(path), "error": str(exc)})
            continue
        findings = lint_crp(text, source=str(path))
        all_findings.extend(findings)
        per_file.append(
            {
                "file": str(path),
                "findings": [
                    {"check": f.check, "severity": f.severity, "message": f.message}
                    for f in findings
                ],
            }
        )

    errors = [f for f in all_findings if f.severity == "error"]
    warnings = [f for f in all_findings if f.severity == "warning"]

    if args.sarif:
        args.sarif.write_text(
            json.dumps(findings_to_sarif(all_findings, corpus=args.dir), indent=2)
            + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(
            json.dumps(
                {
                    "files_scanned": len(targets),
                    "errors": len(errors),
                    "warnings": len(warnings),
                    "results": per_file,
                },
                indent=2,
            )
        )
    else:
        for pf in per_file:
            fs = pf.get("findings", [])
            if not fs:
                continue
            print(f"\n{pf['file']}")
            for f in fs:
                print(f"  [{f['severity']}] ({f['check']}) {f['message']}")
        print(
            f"\n{len(targets)} det-crp artifact(s) scanned · "
            f"{len(errors)} error(s) · {len(warnings)} warning(s)"
        )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
