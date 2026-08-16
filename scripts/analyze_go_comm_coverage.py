#!/usr/bin/env python3
"""Analyze a Go corpus against the Go structure->OTel §5 communication index (FR-4 / IT-5).

Go analogue of analyze_otel_demo_python_coverage.py. ADVISORY tier: detection is IMPORT-ONLY
(no call graph). Walks ``*.go`` under --workdir, calls go_parser.parse_go_imports per file,
computes hyp(f) = the achievable §5 patterns whose import_signatures match a file import, and
reports corpus coverage as an ACHIEVABLE-vs-FLOOR split (floor patterns are excluded from the
achievable denominator — they are correct-absences, not gaps).

This script is now THIN: it carries Go's CoverageAdapter (extensions, import extractor, path
separator) and hands it to the shared ``startd8.coverage_map`` engine. ``_hyp`` / ``analyze`` are
kept as the parity test's surface.

No new parser / regex: imports come from startd8/languages/go_parser.parse_go_imports (FR-4, NR-1).

Spec: docs/design/REQ-crosswalk-go-structure-to-otel-comm-domains.md
Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md

Usage:
    python3 scripts/analyze_go_comm_coverage.py                       # default corpus OSS/Thanos
    python3 scripts/analyze_go_comm_coverage.py --workdir /path/to/go/repo
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from startd8.coverage_map import (
    CoverageAdapter,
    Detector,
    coverage_report,
    render_coverage_md,
    render_sarif,
)
from startd8.languages.go_parser import parse_go_imports

REPO = Path(__file__).resolve().parents[1]
_GEN_PATH = REPO / "scripts" / "gen_go_structure_comm_index.py"
#: Default corpus: real, local, OTel-heavy Go (not fixtures/otel-demo — those are Python ports).
DEFAULT_WORKDIR = REPO.parent / "OSS" / "Thanos"
OUT_DIR = REPO / "docs" / "design" / "go-capability-index"

#: The Go coverage adapter — the 3 real per-language deltas (extensions, extractor, separator).
ADAPTER = CoverageAdapter(
    extensions=frozenset({".go"}),
    extract_imports=parse_go_imports,
    separator="/",
    exclude_segments=frozenset({"vendor"}),
)


def _load_index() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("gen_go_structure_comm_index", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_index()


def _hyp(imports: list[str], achievable: list[dict[str, Any]]) -> list[str]:
    """Import-only hypothesis (collision-safe). Kept as the parity test's entry point."""
    return Detector(ADAPTER).hyp(imports, achievable)


def analyze(workdir: Path) -> dict[str, Any]:
    index = _load_index()
    return coverage_report(ADAPTER, index, workdir, label=("tier", index["tier"]))


def _render_md(r: dict[str, Any]) -> str:
    c = r["coverage"]
    meta_lines = [
        f"**Tier:** {r['tier']} (import-only detection; no call graph)  ",
        f"**Achievable coverage:** **{c['achievable_coverage_percent']}%** "
        f"({c['detected_patterns']}/{c['achievable_patterns']} achievable §5 patterns)  ",
        f"**Floor (excluded — correct-absence):** {', '.join(c['floor_patterns_excluded'])}",
    ]
    return render_coverage_md(
        r, title="# Go — OTel §5 Communication Coverage",
        generator="analyze_go_comm_coverage.py", meta_lines=meta_lines,
        json_sibling="thanos-coverage.json")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR, help="Go corpus root")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "thanos-coverage.json")
    ap.add_argument("--md-out", type=Path, default=OUT_DIR / "thanos-coverage.md")
    ap.add_argument("--no-write", action="store_true", help="Print summary only; write nothing")
    ap.add_argument("--sarif", type=Path, default=None,
                    help="Also write a SARIF 2.1.0 report (GitHub code-scanning / IDE) to this path")
    args = ap.parse_args(argv)

    if not args.workdir.is_dir():
        print(f"error: corpus not found: {args.workdir}", file=sys.stderr)
        return 1

    r = analyze(args.workdir)
    c = r["coverage"]

    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(r, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        args.md_out.write_text(_render_md(r), encoding="utf-8")
        print(f"wrote {args.out}")
        print(f"wrote {args.md_out}")

    if args.sarif is not None:
        args.sarif.parent.mkdir(parents=True, exist_ok=True)
        doc = render_sarif(r, tool_name="otel-comm-coverage-go", corpus=r["corpus"])
        args.sarif.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.sarif}")

    print(f"corpus: {r['corpus']}  files: {r['files_analyzed']}")
    print(f"achievable coverage: {c['achievable_coverage_percent']}% "
          f"({c['detected_patterns']}/{c['achievable_patterns']})  "
          f"floor excluded: {', '.join(c['floor_patterns_excluded'])}")
    for pid in r["detected"]:
        print(f"  detected {pid} ({r['per_pattern_file_counts'][pid]} files)")
    if r["not_evidenced_achievable"]:
        print(f"  not evidenced: {', '.join(r['not_evidenced_achievable'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
