#!/usr/bin/env python3
"""Open Question #2 probe: can TraceQL / span-link traversal express taint reachability?

The design (CODE_OBSERVABILITY_DESIGN.md §2.5, OQ#2) proposes expressing a taint
query as a TraceQL structural query:

    { .code.is_source = true } >> { .code.is_sink = true }

i.e. "an HTTP-handler source span has a DESCENDANT raw-SQL sink span." This script
probes whether that actually answers "does untrusted source X reach SQL sink Y?"

We run THREE traversals over the emitted span structure (out/spans.json):

  (1) CALLS-tree descendant traversal — what TraceQL `>>` (descendant) does NATIVELY
      on the span parent/child tree. Pure structural reachability over call edges.

  (2) DATAFLOW-link traversal — follows ONLY the span-link edges
      (`dataflow_link_span_ids`), which model actual value propagation. This is what
      you need to avoid false positives where a source calls a sink but no DATA
      flows between them.

  (3) The "TraceQL approximation" — emulates `{source} >> {sink}` and reports whether
      the native operator agrees with the true dataflow answer.

Output: a verdict on OQ#2 written to stdout and out/taint_probe_result.json.

Run standalone (after emit.py):
    python3 scripts/spikes/code_observability/taint_query_probe.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
SPANS_PATH = os.path.join(HERE, "out", "spans.json")


def load_spans() -> dict:
    if not os.path.exists(SPANS_PATH):
        print(f"[probe] {SPANS_PATH} missing — run emit.py first.", file=sys.stderr)
        raise SystemExit(2)
    with open(SPANS_PATH) as fh:
        return json.load(fh)


def _index(trace: dict):
    by_id = {s["span_id"]: s for s in trace["spans"]}
    # CALLS tree: parent span_id -> child span_ids (via calls_children element ids)
    elem_to_span = {s["element_id"]: s["span_id"] for s in trace["spans"]}
    calls = defaultdict(list)
    flow = defaultdict(list)
    for s in trace["spans"]:
        for child_elem in s.get("calls_children", []):
            if child_elem in elem_to_span:
                calls[s["span_id"]].append(elem_to_span[child_elem])
        for child_span in s.get("dataflow_link_span_ids", {}).values():
            flow[s["span_id"]].append(child_span)
    return by_id, calls, flow


def _reachable(start: str, adj: dict) -> set:
    seen, q = set(), deque([start])
    while q:
        n = q.popleft()
        for m in adj.get(n, []):
            if m not in seen:
                seen.add(m)
                q.append(m)
    return seen


def _path(start: str, target: str, adj: dict):
    prev = {start: None}
    q = deque([start])
    while q:
        n = q.popleft()
        if n == target:
            out = []
            while n is not None:
                out.append(n)
                n = prev[n]
            return list(reversed(out))
        for m in adj.get(n, []):
            if m not in prev:
                prev[m] = n
                q.append(m)
    return None


def probe(spans: dict) -> dict:
    results = {"traces": [], "verdict": {}}
    any_calls_hit = any_flow_hit = False
    disagreements = 0

    for trace in spans["traces"]:
        by_id, calls, flow = _index(trace)
        sources = [s["span_id"] for s in trace["spans"]
                   if s["attributes"].get("code.is_source")]
        sinks = [s["span_id"] for s in trace["spans"]
                 if s["attributes"].get("code.is_sink")]

        tr = {"root": trace["root"], "findings": []}
        for src in sources:
            for snk in sinks:
                # (1) TraceQL-`>>` analogue: descendant over CALLS tree
                calls_reach = snk in _reachable(src, calls)
                # (2) true dataflow: descendant over DATAFLOW links only
                flow_reach = snk in _reachable(src, flow)
                calls_path = _path(src, snk, calls) if calls_reach else None
                flow_path = _path(src, snk, flow) if flow_reach else None

                def names(p):
                    return [by_id[x]["attributes"]["code.function"] for x in p] if p else None

                any_calls_hit |= calls_reach
                any_flow_hit |= flow_reach
                if calls_reach != flow_reach:
                    disagreements += 1

                tr["findings"].append({
                    "source": by_id[src]["attributes"]["code.function"],
                    "sink": by_id[snk]["attributes"]["code.function"],
                    "traceql_descendant_calls": calls_reach,
                    "dataflow_link_reachable": flow_reach,
                    "calls_path": names(calls_path),
                    "dataflow_path": names(flow_path),
                    "tainted": flow_reach,  # dataflow is the ground truth
                })
        results["traces"].append(tr)

    results["verdict"] = {
        "calls_descendant_found_any": any_calls_hit,
        "dataflow_link_found_any": any_flow_hit,
        "calls_vs_dataflow_disagreements": disagreements,
    }
    return results


def main() -> int:
    spans = load_spans()
    res = probe(spans)

    print("=" * 72)
    print("OPEN QUESTION #2 PROBE — taint reachability via span/link traversal")
    print("=" * 72)
    for tr in res["traces"]:
        print(f"\nTrace root: {tr['root']}")
        if not tr["findings"]:
            print("  (no source/sink pair in this trace)")
        for f in tr["findings"]:
            tag = "TAINTED ⚠" if f["tainted"] else "safe"
            print(f"  {f['source']} -> {f['sink']}: {tag}")
            print(f"     TraceQL `{{source}} >> {{sink}}` (CALLS descendant): "
                  f"{f['traceql_descendant_calls']}")
            print(f"     DATAFLOW-link reachable (value actually flows): "
                  f"{f['dataflow_link_reachable']}")
            if f["calls_path"]:
                print(f"     calls path:    {' -> '.join(f['calls_path'])}")
            if f["dataflow_path"]:
                print(f"     dataflow path: {' -> '.join(f['dataflow_path'])}")

    v = res["verdict"]
    print("\n" + "-" * 72)
    print("VERDICT")
    print("-" * 72)
    print(f"  CALLS-descendant (native TraceQL `>>`) found a source->sink path: "
          f"{v['calls_descendant_found_any']}")
    print(f"  DATAFLOW-link traversal found a true taint path:                  "
          f"{v['dataflow_link_found_any']}")
    print(f"  Disagreements (calls says reachable, dataflow says no, or vice):  "
          f"{v['calls_vs_dataflow_disagreements']}")
    print()
    if v["calls_descendant_found_any"] and v["dataflow_link_found_any"]:
        print("  => TraceQL `>>` over the CALLS span-tree CAN locate candidate")
        print("     source->sink reachability. But it cannot, on its own,")
        print("     distinguish 'value flows' from 'merely calls' — that requires")
        print("     traversing the DATAFLOW span LINKS, which TraceQL does NOT")
        print("     follow transitively (it has no multi-hop link-chase operator).")
        print("     PARTIAL: native `>>` = reachability over nesting; multi-hop")
        print("     taint over links needs a thin graph helper. See findings doc.")

    # --- Synthetic divergence demo -------------------------------------------
    # Construct the case that proves WHY native `>>` is insufficient: a source
    # that CALLS a chain reaching a sink, but where the tainted value does NOT
    # flow along that chain (e.g. it calls log(constant) then later db.Exec of a
    # SAFE constant). Native CALLS-descendant `>>` would FALSE-POSITIVE here;
    # DATAFLOW-link traversal correctly says "not tainted".
    demo_calls = {"src": ["mid"], "mid": ["sink"]}          # source >> sink via CALLS
    demo_flow = {"src": [], "mid": []}                       # but NO value flows
    calls_fp = "sink" in _reachable("src", demo_calls)
    flow_fp = "sink" in _reachable("src", demo_flow)
    res["synthetic_divergence_demo"] = {
        "description": "source calls a sink-reaching chain but no value flows",
        "traceql_descendant_calls": calls_fp,   # True  -> would false-positive
        "dataflow_link_reachable": flow_fp,      # False -> correct answer
        "demonstrates": "native `>>` over CALLS tree alone causes false positives; "
                        "link-chase over DATAFLOW is required for precision",
    }
    print("\n" + "-" * 72)
    print("SYNTHETIC DIVERGENCE DEMO (why CALLS `>>` alone is insufficient)")
    print("-" * 72)
    print("  Scenario: source CALLS a chain reaching a sink, but no value flows.")
    print(f"    TraceQL `{{source}} >> {{sink}}` (CALLS):  {calls_fp}  <- FALSE POSITIVE")
    print(f"    DATAFLOW-link reachable:                {flow_fp}  <- correct (safe)")

    out = os.path.join(HERE, "out", "taint_probe_result.json")
    with open(out, "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"\n[probe] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
