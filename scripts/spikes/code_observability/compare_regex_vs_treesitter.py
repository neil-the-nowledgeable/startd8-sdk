#!/usr/bin/env python3
"""Side-by-side evidence: SDK regex go_parser vs. tree-sitter extractor.

Demonstrates the depth gap motivating the design: the existing regex parser
extracts declarations but NO call graph (its docstring says so), while the
tree-sitter extractor resolves nested call sites and dataflow edges.

Run (needs the SDK importable):
    PYTHONPATH=src python3 scripts/spikes/code_observability/compare_regex_vs_treesitter.py
"""
from __future__ import annotations

import dataclasses
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixture", "sample.go")

# make the spike's extractor importable when run from repo root
sys.path.insert(0, HERE)


def regex_summary() -> dict:
    try:
        from startd8.languages.go_parser import parse_go_source
    except Exception as exc:  # noqa: BLE001
        return {"error": f"could not import SDK go_parser ({exc}); "
                         "run with PYTHONPATH=src"}
    res = parse_go_source(open(FIXTURE).read())
    out = {"type": type(res).__name__, "call_edges": "NONE (not extracted)"}
    if dataclasses.is_dataclass(res):
        for f in dataclasses.fields(res):
            v = getattr(res, f.name)
            out[f.name] = len(v) if isinstance(v, list) else v
    return out


def treesitter_summary() -> dict:
    from extractor import extract
    g = extract(FIXTURE)
    calls = [(e.src.split("::")[-1], e.dst.split("::")[-1])
             for e in g.edges if e.kind == "CALLS"]
    flow = [(e.src.split("::")[-1], e.dst.split("::")[-1], e.detail)
            for e in g.edges if e.kind == "DATAFLOW"]
    return {
        "functions": sum(1 for e in g.elements if e.kind == "function"),
        "call_edges": calls,
        "dataflow_edges": flow,
        "taint_sinks": [e.id.split('::')[-1] for e in g.elements if e.is_sink],
    }


def main() -> int:
    print("=" * 72)
    print("REGEX go_parser.py (SDK) vs TREE-SITTER extractor.py (spike)")
    print("=" * 72)
    print("\n[regex] startd8.languages.go_parser.parse_go_source:")
    for k, v in regex_summary().items():
        print(f"   {k}: {v}")
    print("\n   docstring limitation (go_parser.py:17):")
    print("   'Does not parse function bodies (no call graph extraction)'")

    print("\n[tree-sitter] spike extractor:")
    ts = treesitter_summary()
    print(f"   functions: {ts['functions']}")
    print(f"   call edges ({len(ts['call_edges'])}):")
    for a, b in ts["call_edges"]:
        print(f"      {a} -> {b}")
    print(f"   dataflow edges ({len(ts['dataflow_edges'])}):")
    for a, b, d in ts["dataflow_edges"]:
        print(f"      {a} -> {b}   [{d}]")
    print(f"   taint sinks: {ts['taint_sinks']}")
    print("\nConclusion: regex gives declarations; tree-sitter gives the call/")
    print("dataflow graph required for cross-file reachability + taint analysis.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
