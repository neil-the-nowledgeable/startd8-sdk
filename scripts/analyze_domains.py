#!/usr/bin/env python3
"""Unified §5 domain report: coverage (imports) + precision (contract IDLs) in one pass.

Runs a language's coverage analyzer AND the precision layer over a repo, then joins them per
semconv_domain — so one report answers "does it touch domain X?" AND "which operations?".

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md (§ three-tier stack).

Usage:
    python3 scripts/analyze_domains.py --workdir /path/to/repo --lang java
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

from startd8.coverage_map.precision import PRECISION_DOMAINS, extract_precision
from startd8.coverage_map.unified import unify

REPO = Path(__file__).resolve().parents[1]
_ANALYZERS = {lang: REPO / "scripts" / f"analyze_{lang}_comm_coverage.py" for lang in ("go", "java", "node")}


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def analyze(workdir: Path, lang: str) -> dict:
    analyzer = _load(_ANALYZERS[lang], f"analyze_{lang}")
    coverage = analyzer.analyze(workdir)
    precision = {dom: extract_precision(workdir, dom) for dom in PRECISION_DOMAINS}
    return {"repo": str(workdir), "lang": lang, "coverage_percent": coverage["coverage"]["achievable_coverage_percent"],
            "unified": unify(coverage, precision)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument("--lang", choices=sorted(_ANALYZERS), required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if not args.workdir.is_dir():
        print(f"error: repo not found: {args.workdir}", file=sys.stderr)
        return 1

    r = analyze(args.workdir, args.lang)
    if args.out:
        args.out.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")

    s = r["unified"]["summary"]
    print(f"repo: {r['repo']}  ({r['lang']} coverage {r['coverage_percent']}%)")
    print(f"  covered+precise={s['covered_and_precise']} · covered-only={s['covered_only']} · precise-only={s['precise_only']}")
    _label = {"covered+precise": "✓✓", "covered-only": "✓ ", "precise-only": " ◆", "absent": "  "}
    for dom, d in r["unified"]["domains"].items():
        if d["state"] == "absent":
            continue
        cov = f"{d['coverage_files']} files" if d["covered"] else "—"
        prec = f"{d['precise_operations']} ops via {d['idl_type']} ({', '.join(d['idl_files'])})" if d["precision_available"] else "no IDL"
        print(f"  {_label[d['state']]} {dom:14} coverage: {cov:12}  precision: {prec}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
