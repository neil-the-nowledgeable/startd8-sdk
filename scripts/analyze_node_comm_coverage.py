#!/usr/bin/env python3
"""Analyze a Node/JS/TS corpus against the Node structure->OTel §5 index (FR-4 / IT-5).

Imports-only detection. nodejs_parser exposes NO import extractor, so this analyzer owns a thin
ESM/CJS import regex (NR-1: nodejs_parser is untouched). Walks *.{js,mjs,cjs,ts,tsx}, matches import
specifiers against φ, reports achievable-vs-floor coverage. Call-site φ is resolution-pending
(scip-typescript, CKG Phase 1 — the nearest unlock).

This script is now THIN: it owns the ESM/CJS ``extract_imports`` regex (the one NEW mechanism) and
carries it in a CoverageAdapter to the shared ``startd8.coverage_map`` engine. ``extract_imports`` /
``_hyp`` / ``analyze`` stay as the parity test's surface.

Spec: docs/design/REQ-crosswalk-node-structure-to-otel-comm-domains.md · Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md

Usage:
    python3 scripts/analyze_node_comm_coverage.py                 # default corpus MCP/
    python3 scripts/analyze_node_comm_coverage.py --workdir /path/to/node/repo
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
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

REPO = Path(__file__).resolve().parents[1]
_GEN_PATH = REPO / "scripts" / "gen_node_structure_comm_index.py"
DEFAULT_WORKDIR = REPO.parent / "MCP"
OUT_DIR = REPO / "docs" / "design" / "node-capability-index"
_EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx"}
_DETECTOR_LABEL = "import-only (ESM+CJS; advisory; call-site φ is scip-typescript-pending)"

# The one new mechanism (FR-4): ESM `import … from '<spec>'` / `import '<spec>'` (+ export re-export),
# and CJS `require('<spec>')`. nodejs_parser has no import extractor, so it lives here.
_ESM_FROM = re.compile(r"""(?:import|export)\b[^;\n]*?\bfrom\s*['"]([^'"]+)['"]""")
_ESM_BARE = re.compile(r"""^\s*import\s+['"]([^'"]+)['"]""", re.MULTILINE)
_CJS = re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)""")


def extract_imports(source: str) -> set[str]:
    return (set(_ESM_FROM.findall(source)) | set(_ESM_BARE.findall(source)) | set(_CJS.findall(source)))


#: The Node coverage adapter — the inline ESM/CJS extractor + npm-specifier ('/' subpath) matching.
ADAPTER = CoverageAdapter(
    extensions=frozenset(_EXTS),
    extract_imports=extract_imports,
    separator="/",
    exclude_segments=frozenset({"node_modules", "dist", "build"}),
    exclude_suffixes=(".d.ts", ".min.js"),
)


def _load_index() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("gen_node_structure_comm_index", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_index()


def _hyp(imports, achievable: list[dict[str, Any]]) -> list[str]:
    """Import-only hypothesis (npm specifier / subpath match). Kept as the parity test's entry point."""
    return Detector(ADAPTER).hyp(imports, achievable)


def analyze(workdir: Path) -> dict[str, Any]:
    return coverage_report(ADAPTER, _load_index(), workdir, label=("detector", _DETECTOR_LABEL))


def _render_md(r: dict[str, Any]) -> str:
    c = r["coverage"]
    meta_lines = [
        f"**Detector:** {r['detector']}  ",
        f"**Achievable coverage:** **{c['achievable_coverage_percent']}%** ({c['detected_patterns']}/{c['achievable_patterns']})  ",
        f"**Floor excluded:** {', '.join(c['floor_patterns_excluded'])}",
    ]
    return render_coverage_md(
        r, title="# Node/JS/TS — OTel §5 Communication Coverage",
        generator="analyze_node_comm_coverage.py", meta_lines=meta_lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR, help="Node corpus root")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "mcp-coverage.json")
    ap.add_argument("--md-out", type=Path, default=OUT_DIR / "mcp-coverage.md")
    ap.add_argument("--no-write", action="store_true")
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
        print(f"wrote {args.out}"); print(f"wrote {args.md_out}")

    if args.sarif is not None:
        args.sarif.parent.mkdir(parents=True, exist_ok=True)
        doc = render_sarif(r, tool_name="otel-comm-coverage-node", corpus=r["corpus"])
        args.sarif.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.sarif}")
    print(f"corpus: {r['corpus']}  files: {r['files_analyzed']}")
    print(f"achievable coverage: {c['achievable_coverage_percent']}% ({c['detected_patterns']}/{c['achievable_patterns']})"
          f"  floor excluded: {', '.join(c['floor_patterns_excluded'])}")
    for pid in r["detected"]:
        print(f"  detected {pid} ({r['per_pattern_file_counts'][pid]} files)")
    if r["not_evidenced_achievable"]:
        print(f"  not evidenced: {', '.join(r['not_evidenced_achievable'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
