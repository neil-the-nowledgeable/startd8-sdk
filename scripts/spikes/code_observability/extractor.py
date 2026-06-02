#!/usr/bin/env python3
"""Tree-sitter Go extractor -> CodeGraph IR (Phase 0 spike).

Builds a lightweight CodeGraph (CodeElement nodes + typed edges) for a Go
source file using a *real* tree-sitter AST. Unlike the regex-based
``languages/go_parser.py`` in the SDK, this resolves:

  * accurate call sites (including NESTED calls: ``bar(baz(x))`` yields BOTH
    a CALLS edge to ``bar`` and to ``baz``)
  * the enclosing function for every call (so CALLS edges have a real source)
  * a coarse DATAFLOW edge: when a function passes one of ITS OWN parameters
    (or a value derived from one) as an argument to a callee, we record a
    parameter-to-callee dataflow edge. This is what lets the emitter build
    span links that model taint propagation.

Edge kinds emitted:
  CALLS      caller_func  -> callee_func
  DATAFLOW   caller_func  -> callee_func   (a tainted/derived value flows in)
  DEFINES    module       -> function
  REFERENCES function     -> identifier-name  (coarse, used for source/sink tags)

Run standalone:
    python3 scripts/spikes/code_observability/extractor.py            # uses bundled fixture
    python3 scripts/spikes/code_observability/extractor.py path/to.go
    python3 scripts/spikes/code_observability/extractor.py --out graph.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional

import tree_sitter as ts
import tree_sitter_go as tsgo

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_FIXTURE = os.path.join(HERE, "fixture", "sample.go")

# Heuristic markers that classify a function as a taint source or sink.
# These are intentionally simple (this is a spike) — the point of the probe is
# that the GRAPH (not the keywords) decides reachability.
SOURCE_MARKERS = ("r.URL.Query", "Request", "FormValue", "Header.Get")
SINK_CALLS = ("db.Query", "db.Exec", "Query", "Exec")  # raw driver calls
SAFE_PARAM_HINT = "args..."  # parameterized call signal


# --------------------------------------------------------------------------- #
# CodeGraph IR
# --------------------------------------------------------------------------- #
@dataclass
class CodeElement:
    id: str
    kind: str  # module | function
    language: str
    file: str
    start_line: int
    end_line: int
    signature: str = ""
    docstring: str = ""
    # spike-only analysis tags
    is_source: bool = False
    is_sink: bool = False
    raw_concat_sql: bool = False  # builds SQL by string concatenation


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # CALLS | DATAFLOW | DEFINES | REFERENCES
    detail: str = ""


@dataclass
class CodeGraph:
    language: str
    module: str
    file: str
    elements: list[CodeElement] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "language": self.language,
            "module": self.module,
            "file": self.file,
            "elements": [asdict(e) for e in self.elements],
            "edges": [asdict(e) for e in self.edges],
        }


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def _node_text(node: ts.Node, src: bytes) -> str:
    return src[node.start_byte : node.end_byte].decode("utf-8", "replace")


def _callee_name(call_node: ts.Node, src: bytes) -> Optional[str]:
    """Return the textual callee of a call_expression (e.g. 'bar', 'db.Query')."""
    fn = call_node.child_by_field_name("function")
    if fn is None:
        return None
    return _node_text(fn, src)


def _collect_calls(node: ts.Node, src: bytes, out: list[ts.Node]) -> None:
    """Recursively collect every call_expression under `node` (captures nested)."""
    if node.type == "call_expression":
        out.append(node)
    for c in node.children:
        _collect_calls(c, src, out)


def _params_of(func_node: ts.Node, src: bytes) -> list[str]:
    names: list[str] = []
    plist = func_node.child_by_field_name("parameters")
    if plist is None:
        return names
    for child in plist.children:
        if child.type == "parameter_declaration":
            for sub in child.children:
                if sub.type == "identifier":
                    names.append(_node_text(sub, src))
    return names


def _arg_identifiers(call_node: ts.Node, src: bytes) -> list[str]:
    """Identifier names appearing anywhere inside the call's argument list."""
    ids: list[str] = []
    args = call_node.child_by_field_name("arguments")
    if args is None:
        return ids

    def rec(n: ts.Node) -> None:
        if n.type == "identifier":
            ids.append(_node_text(n, src))
        for c in n.children:
            rec(c)

    for c in args.children:
        rec(c)
    return ids


def extract(go_path: str) -> CodeGraph:
    with open(go_path, "rb") as fh:
        src = fh.read()

    lang = ts.Language(tsgo.language())
    parser = ts.Parser(lang)
    tree = parser.parse(src)
    root = tree.root_node

    # module / package name
    module = "main"
    for c in root.children:
        if c.type == "package_clause":
            for sub in c.children:
                if sub.type == "package_identifier":
                    module = _node_text(sub, src)

    graph = CodeGraph(language="go", module=module, file=go_path)
    module_id = f"go::module::{module}"
    graph.elements.append(
        CodeElement(
            id=module_id,
            kind="module",
            language="go",
            file=go_path,
            start_line=root.start_point[0] + 1,
            end_line=root.end_point[0] + 1,
            signature=f"package {module}",
        )
    )

    # first pass: function declarations -> elements + DEFINES edges
    func_nodes: dict[str, ts.Node] = {}
    for c in root.children:
        if c.type != "function_declaration":
            continue
        name_node = c.child_by_field_name("name")
        if name_node is None:
            continue
        fname = _node_text(name_node, src)
        func_nodes[fname] = c
        fid = f"go::func::{fname}"
        sig = _node_text(c, src).split("{", 1)[0].strip()
        body_text = _node_text(c, src)

        is_source = any(m in body_text for m in SOURCE_MARKERS)
        # raw concat SQL: body contains a string literal SELECT/INSERT etc. AND '+'
        raw_concat = (
            ("SELECT" in body_text or "INSERT" in body_text or "UPDATE" in body_text)
            and '" +' in body_text.replace(" ", " ")
            or '" + ' in body_text
        )

        graph.elements.append(
            CodeElement(
                id=fid,
                kind="function",
                language="go",
                file=go_path,
                start_line=c.start_point[0] + 1,
                end_line=c.end_point[0] + 1,
                signature=sig,
                is_source=is_source,
                raw_concat_sql=bool(raw_concat),
            )
        )
        graph.edges.append(Edge(src=module_id, dst=fid, kind="DEFINES"))

    func_names = set(func_nodes)

    # second pass: per-function call extraction (CALLS + DATAFLOW + sink tagging)
    for fname, fnode in func_nodes.items():
        fid = f"go::func::{fname}"
        params = set(_params_of(fnode, src))
        calls: list[ts.Node] = []
        _collect_calls(fnode, src, calls)

        elem = next(e for e in graph.elements if e.id == fid)

        for call in calls:
            callee = _callee_name(call, src)
            if not callee:
                continue

            # SINK tagging: does this function itself call a raw driver method?
            base = callee.split("(")[0]
            if base in SINK_CALLS or callee in SINK_CALLS:
                # parameterized? db.Query(query, args...) has >1 arg -> safe
                argtext = ""
                args = call.child_by_field_name("arguments")
                if args is not None:
                    argtext = _node_text(args, src)
                parameterized = "," in argtext
                if not parameterized:
                    elem.is_sink = True
                graph.edges.append(
                    Edge(src=fid, dst=f"go::extern::{callee}", kind="REFERENCES",
                         detail="parameterized" if parameterized else "raw_sql")
                )

            # CALLS edge only for intra-module functions (resolvable targets)
            if callee in func_names:
                graph.edges.append(Edge(src=fid, dst=f"go::func::{callee}", kind="CALLS"))

                # DATAFLOW: does this call pass one of THIS function's params
                # (or a locally-derived value) as an argument?
                arg_ids = set(_arg_identifiers(call, src))
                flowing = arg_ids & params
                if flowing:
                    graph.edges.append(
                        Edge(src=fid, dst=f"go::func::{callee}", kind="DATAFLOW",
                             detail="param:" + ",".join(sorted(flowing)))
                    )
                else:
                    # local var passed (e.g. query := buildQuery(id); execSQL(query))
                    # coarse: any identifier argument => potential dataflow
                    if arg_ids:
                        graph.edges.append(
                            Edge(src=fid, dst=f"go::func::{callee}", kind="DATAFLOW",
                                 detail="local:" + ",".join(sorted(arg_ids)))
                        )

    return graph


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Tree-sitter Go -> CodeGraph extractor (spike)")
    ap.add_argument("path", nargs="?", default=DEFAULT_FIXTURE, help="Go source file")
    ap.add_argument("--out", default=None, help="write CodeGraph JSON here")
    args = ap.parse_args(argv)

    graph = extract(args.path)
    out_path = args.out or os.path.join(HERE, "out", "code_graph.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(graph.to_json(), fh, indent=2)

    n_calls = sum(1 for e in graph.edges if e.kind == "CALLS")
    n_flow = sum(1 for e in graph.edges if e.kind == "DATAFLOW")
    print(f"[extractor] parsed {args.path}")
    print(f"[extractor] elements={len(graph.elements)} "
          f"CALLS={n_calls} DATAFLOW={n_flow}")
    sources = [e.id for e in graph.elements if e.is_source]
    sinks = [e.id for e in graph.elements if e.is_sink]
    print(f"[extractor] taint sources={sources}")
    print(f"[extractor] taint sinks={sinks}")
    print(f"[extractor] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
