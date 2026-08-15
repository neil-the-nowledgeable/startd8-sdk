#!/usr/bin/env python3
"""Tier-2 precision analyzer: report a repo's precise §5 operations from its contract IDLs.

The coverage analyzers (Tier 1) say a repo TOUCHES http/rpc/db. This says WHICH operations, by
parsing the domain's contract IDL via the SDK's existing parsers (http→OpenAPI, rpc→proto, db→Prisma).
Precision is available only where an IDL exists — otherwise coverage-only (correct-absence).

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md · Spec: docs/design/REQ-precision-layer-contract-idl-operations.md

Usage:
    python3 scripts/analyze_precision.py --workdir /path/to/repo
    python3 scripts/analyze_precision.py --workdir /path/to/repo --domain http --out prec.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from startd8.coverage_map.precision import PRECISION_DOMAINS, extract_precision


def analyze(workdir: Path, domains: list[str]) -> dict:
    return {"repo": str(workdir), "domains": {d: extract_precision(workdir, d) for d in domains}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", type=Path, required=True, help="repo root")
    ap.add_argument("--domain", choices=sorted(PRECISION_DOMAINS), action="append",
                    help="limit to domain(s); default all")
    ap.add_argument("--out", type=Path, default=None, help="write full JSON here")
    ap.add_argument("--sample", type=int, default=5, help="ops to print per IDL file")
    args = ap.parse_args(argv)
    if not args.workdir.is_dir():
        print(f"error: repo not found: {args.workdir}", file=sys.stderr)
        return 1

    r = analyze(args.workdir, args.domain or sorted(PRECISION_DOMAINS))
    if args.out:
        args.out.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")

    print(f"repo: {r['repo']}")
    for dom, res in r["domains"].items():
        if not res["precision_available"]:
            print(f"  {dom:5} — no {res['idl_type']} IDL found (coverage-only)")
            continue
        print(f"  {dom:5} — {res['total_operations']} operations from {res['idl_type']} "
              f"({len(res['idl_files'])} file(s))")
        for f in res["idl_files"]:
            print(f"    {f['path']}: {f['count']} ops")
            for op in f["operations"][:args.sample]:
                print(f"      · {op['op']}")
        for e in res["parse_errors"]:
            print(f"    ⚠ {e['path']}: {e['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
