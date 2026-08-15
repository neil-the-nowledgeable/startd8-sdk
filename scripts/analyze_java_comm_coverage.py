#!/usr/bin/env python3
"""Analyze a Java corpus against the Java structure->OTel §5 index (FR-4 / IT-5).

Java analogue of analyze_go_comm_coverage.py, with the NEW dimension: detection is IMPORT +
ANNOTATION. Walks ``*.java`` under --workdir, uses go_parser's Java twin —
``parse_java_imports`` (imports) + ``parse_java_source`` (elements carry ``.annotations``) — and
reports coverage AND an **import-hits vs annotation-hits breakdown** (the evidence for whether the
annotation axis earns its place over imports alone).

This script is now THIN: it carries Java's CoverageAdapter (with ``has_annotations=True`` + the
annotation extractor) and hands it to the shared ``startd8.coverage_map`` engine. ``_hyp`` /
``analyze`` stay as the parity test's surface.

No new parser/regex (FR-4, NR-1). Call-site φ is resolution-pending (SCIP-java) and out of scope.

Spec: docs/design/REQ-crosswalk-java-structure-to-otel-comm-domains.md
Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md

Usage:
    python3 scripts/analyze_java_comm_coverage.py                 # default corpus OSS/kestra
    python3 scripts/analyze_java_comm_coverage.py --workdir /path/to/java/repo
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
from startd8.languages.java_parser import parse_java_imports, parse_java_source

REPO = Path(__file__).resolve().parents[1]
_GEN_PATH = REPO / "scripts" / "gen_java_structure_comm_index.py"
#: Default corpus: real, local, framework-rich Java (Micronaut/JAX-RS/gRPC/JPA).
DEFAULT_WORKDIR = REPO.parent / "OSS" / "kestra"
OUT_DIR = REPO / "docs" / "design" / "java-capability-index"
_DETECTOR_LABEL = "import + annotation (resolution-blind; call-site φ is SCIP-pending)"


def _java_annotations(src: str) -> set[str]:
    return {a for el in parse_java_source(src) for a in el.annotations}


#: The Java coverage adapter — import+annotation axis (the one NEW delta vs Go/Node).
ADAPTER = CoverageAdapter(
    extensions=frozenset({".java"}),
    extract_imports=parse_java_imports,
    separator=".",
    exclude_segments=frozenset({"vendor", "build", "target"}),
    has_annotations=True,
    extract_annotations=_java_annotations,
)


def _load_index() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("gen_java_structure_comm_index", _GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_index()


def _hyp(imports: list[str], annotations: set[str], achievable: list[dict[str, Any]]):
    """Import+annotation hypothesis: {pattern_id: 'import'|'annotation'|'both'}. Parity test entry."""
    return Detector(ADAPTER).hyp_signals(imports, annotations, achievable)


def analyze(workdir: Path) -> dict[str, Any]:
    return coverage_report(ADAPTER, _load_index(), workdir, label=("detector", _DETECTOR_LABEL))


def _render_md(r: dict[str, Any]) -> str:
    c = r["coverage"]
    meta_lines = [
        f"**Detector:** {r['detector']}  ",
        f"**Achievable coverage:** **{c['achievable_coverage_percent']}%** "
        f"({c['detected_patterns']}/{c['achievable_patterns']})  ",
        f"**Annotation axis marginal:** {r['annotation_axis']['marginal_patterns']} pattern(s) detected "
        f"ONLY via annotation — {', '.join(r['annotation_axis']['detected_via_annotation_only']) or '(none)'}",
        f"**Floor excluded:** {', '.join(c['floor_patterns_excluded'])}",
    ]
    return render_coverage_md(
        r, title="# Java — OTel §5 Communication Coverage",
        generator="analyze_java_comm_coverage.py", meta_lines=meta_lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR, help="Java corpus root")
    ap.add_argument("--out", type=Path, default=OUT_DIR / "kestra-coverage.json")
    ap.add_argument("--md-out", type=Path, default=OUT_DIR / "kestra-coverage.md")
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
        print(f"wrote {args.out}")
        print(f"wrote {args.md_out}")

    if args.sarif is not None:
        args.sarif.parent.mkdir(parents=True, exist_ok=True)
        doc = render_sarif(r, tool_name="otel-comm-coverage-java", corpus=r["corpus"])
        args.sarif.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.sarif}")

    print(f"corpus: {r['corpus']}  files: {r['files_analyzed']}")
    print(f"achievable coverage: {c['achievable_coverage_percent']}% "
          f"({c['detected_patterns']}/{c['achievable_patterns']})  floor excluded: {', '.join(c['floor_patterns_excluded'])}")
    print(f"annotation-axis marginal: {r['annotation_axis']['marginal_patterns']} "
          f"({', '.join(r['annotation_axis']['detected_via_annotation_only']) or 'none'})")
    for pid in r["detected"]:
        s = r["per_pattern_signal_counts"][pid]
        print(f"  {pid}: import={s['import']} annotation={s['annotation']} both={s['both']}")
    if r["not_evidenced_achievable"]:
        print(f"  not evidenced: {', '.join(r['not_evidenced_achievable'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
