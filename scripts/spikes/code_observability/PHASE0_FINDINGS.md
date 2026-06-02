# Code Observability — Phase 0 Spike Findings

> **Date:** 2026-06-01
> **Scope:** Validate the end-to-end pipeline (Go source → tree-sitter CodeGraph →
> OTel signals → query) and probe **Open Question #2**: *can TraceQL / span-link
> traversal express data-flow (taint) reachability, or do we need a thin graph
> helper on top?*
> **Status:** Spike complete. Pipeline runs end-to-end against **real Tempo**.
> Verdict on OQ#2 below: **PARTIAL — yes for reachability candidates, no for
> precise multi-hop taint; a thin graph helper is needed.**

---

## 1. What was built (all under `scripts/spikes/code_observability/`)

| Artifact | Result |
|----------|--------|
| `fixture/sample.go` | Go program with a 3-level tainted call chain (`handleRequest`→`buildQuery`/`execSQL`→`rawDBExec`) and a SAFE parameterized parallel path (`handleSafeRequest`→`execSQLParams`). |
| `extractor.py` | tree-sitter Go → `CodeGraph` IR. Emitted **7 functions, 5 CALLS edges, 4 DATAFLOW edges**, correctly tagged 2 sources + 1 sink. |
| `emit.py` | CodeGraph → OTel. **16 metric datapoints**, **2 trace trees / 7 spans / 4 dataflow links**. Exported to **real Tempo via OTLP gRPC `localhost:4317`** + JSON mirror. |
| `taint_query_probe.py` | Traverses spans two ways (CALLS-descendant vs DATAFLOW-link) + a synthetic divergence demo. |
| `compare_regex_vs_treesitter.py` | Side-by-side: SDK regex parser (0 call edges) vs tree-sitter (full call/dataflow graph). |

Everything is read-only; no SDK module was modified.

---

## 2. What worked

**End-to-end pipeline runs.** `extract → emit → query` works and the taint path is
detectable at the far end. Both `--no-otlp` (console+JSON) and live-OTLP modes work.

**OTLP infra WAS reachable.** A full kind-based o11y stack was running
(`o11y-dev-control-plane`: Grafana :3000, Mimir :9009, Loki :3100, Tempo :3200,
OTLP :4317/:4318). Spans landed in Tempo and are queryable:

```
GET /api/search?tags=service.name=code-observability-spike
→ traces: handleRequest (d378c19…), handleSafeRequest (ef4d094…), …
```

**A real TraceQL taint query ran against Tempo and gave the right answer:**

```traceql
{ span.code.is_source = true } >> { span.code.is_sink = true }
```
→ matched **exactly** `handleRequest` (the tainted trace); the safe
`handleSafeRequest` trace was **correctly excluded** (it has no sink span).
This is the headline pipeline validation: code structure emitted as spans is
queryable with the *same* TraceQL surface used for business o11y, no new language.

---

## 3. tree-sitter vs. regex — the evidence

`compare_regex_vs_treesitter.py` run on the identical fixture:

| | SDK regex `go_parser.py` | tree-sitter `extractor.py` |
|---|---|---|
| Call edges | **0** (none extracted) | **5** (incl. cross-function chain) |
| Dataflow edges | 0 | **4** (param/local provenance) |
| Nested calls (`bar(baz(x))`) | invisible | both `bar` and `baz` resolved |
| Taint sink detection | n/a | `rawDBExec` flagged; `execSQLParams` correctly NOT flagged |

The SDK parser's own docstring confirms the gap (`go_parser.py:17`):
> *"Does not parse function bodies (no call graph extraction)"*

tree-sitter (ABI 15 grammar, partial-file tolerant, MIT, no build step) gives the
real AST the design needs — and it parses **without compiling the code**, which is
exactly the inner-loop property CodeQL lacks (design §1.3 #2). Confirmed.

---

## 4. Open Question #2 verdict — TraceQL expressiveness for data-flow

**Verdict: PARTIAL. TraceQL natively expresses *structural reachability* over the
call-span tree, but NOT precise multi-hop *data-flow* over span links. A thin
graph-traversal helper is required for sound taint analysis.**

### 4a. What TraceQL DOES natively (proven against Tempo)
- The descendant operator `>>` over the **CALLS span tree** answers
  *"does a source span have a sink descendant?"* — and it ran correctly against
  live Tempo, isolating the tainted trace and excluding the safe one.
- This is genuinely useful as a **coarse candidate filter**: "which entrypoints
  can structurally reach a dangerous sink."

### 4b. Where TraceQL is INSUFFICIENT
1. **`>>` traverses span *nesting* (parent/child = CALLS), not span *links***.
   TraceQL has no operator that **chases span links transitively**. A data-flow
   path that hops source→A→B→sink via DATAFLOW *links* (not call nesting) is not
   expressible as a multi-hop link query. In this spike we made CALLS and DATAFLOW
   coincide so `>>` happened to work; in real code the taint path is a *subset* of
   the call tree, and the difference is exactly the false-positive surface.

2. **`>>` cannot distinguish "calls" from "value flows."** The synthetic
   divergence demo in `taint_query_probe.py` proves this: a source that CALLS a
   sink-reaching chain but where **no value flows** is a **false positive** under
   `>>` (returns reachable=True) while DATAFLOW-link traversal correctly returns
   not-tainted. Replacing `query_prime/security`'s keyword matching with `>>`
   alone would trade one class of false positives (keyword) for another
   (call-reachability without flow).

3. **No path-constraint / sanitizer awareness.** Real taint analysis must say
   "tainted *unless* a sanitizer node is on the path." TraceQL has no notion of
   "path must/most-not contain node with property P" across an arbitrary edge
   type. CodeQL's path queries do; TraceQL does not.

4. **Links are single-hop metadata, not first-class query edges.** OTel span links
   are designed for trace-to-trace causal hints, not for being walked as a graph.
   Tempo indexes spans within a trace; it does not provide transitive link
   closure.

### 4c. Conclusion
- **Reachability candidate detection:** TraceQL `>>` — **yes, use it.** Cheap,
  native, already proven here. Good as a Layer-3 first-pass filter and dashboard.
- **Sound taint (flow-sensitive, sanitizer-aware, multi-hop over DATAFLOW):**
  **needs a thin graph helper** that loads the CodeGraph (or the span+link mirror)
  and runs BFS/DFS over the DATAFLOW edge type with path predicates. That helper
  is ~the `taint_query_probe.py` traversal, productized. It is *thin* (a few
  hundred lines) and operates on data we already emit.

This matches the design's own hedge in §2.5 / OQ#2 ("…or do we need a thin
graph-query helper on top?"). Answer: **yes, on top — TraceQL for the coarse
filter, a graph helper for precision.** Do not over-invest in trying to force
data-flow into pure TraceQL.

---

## 5. Cardinality observations (feeds OQ#1)

- This 87-line fixture → 7 function spans + 4 links + 16 metric datapoints. Linear
  in functions for spans; CALLS edges drive child fan-out; DATAFLOW links are a
  subset of calls.
- **Projection:** spans scale ~1:1 with functions, and per-trace span count scales
  with the size of a call tree rooted at an entrypoint. A large monorepo with deep
  call graphs would produce very large single traces — Tempo's per-trace limits
  (and search cost of deep `>>`) will bite. The design's OQ#1 mitigations
  (per-module sub-traces, depth caps) look necessary, not optional.
- **Label cardinality:** metrics labeled per `element` (`code_fan_in`/`fan_out`)
  multiply datapoints by function count. For Mimir this is the usual high-cardinality
  risk; prefer per-module aggregates for trended gauges and reserve per-element
  detail for logs (LogQL), as the design's three-signal split already suggests.
- **Emission model caveat (found during the spike):** OTel span **links require
  the target SpanContext to exist at creation time**, so a parent cannot link a
  not-yet-created child. We emit the call tree **top-down with real parent/child
  nesting** (so `>>` works in Tempo) and record DATAFLOW link targets as a resolved
  `dataflow_link_span_ids` attribute. A production emitter wanting *native* OTel
  Link objects for DATAFLOW must pre-allocate span IDs in a first pass. Minor, but
  Phase 1 should decide: DATAFLOW as native Links vs. as resolved-ID attributes.

---

## 6. Recommendation: proceed to Phase 1, with adjustments

**Proceed.** The core thesis holds: code structure emitted as OTel telemetry is
queryable with the existing PromQL/LogQL/TraceQL surface, tree-sitter closes the
Go depth gap legally and without a build, and a real taint query ran end-to-end.

Adjustments for Phase 1:

1. **Plan for a thin graph-traversal helper from the start** (Layer 3b). Don't
   promise pure-TraceQL taint. TraceQL = coarse reachability filter; helper =
   precise, sanitizer-aware flow over the DATAFLOW edge type. (Resolves OQ#2.)
2. **Decide the DATAFLOW emission contract** — native OTel Links (pre-allocated
   IDs, two-pass) vs. resolved-ID attributes. Lock it in the `CodeGraph`/span
   schema before wiring `forward_manifest_extractor.py`.
3. **Harden dataflow extraction.** The spike's DATAFLOW edge is coarse
   (param/local identifier match). Real flow-sensitivity (assignments,
   intermediate vars, field access, sanitizer recognition) is the hard part and
   the main Phase 2/3 risk — scope it explicitly.
4. **Build in cardinality controls now** (OQ#1): per-module sub-traces + a depth
   cap, and per-module (not per-element) trended gauges, before pointing this at a
   real benchmark target like online-boutique.
5. **Keep tree-sitter core pinned ≥ 0.25** (ABI 15). Note the pre-existing
   `codebleu` pin (`tree-sitter<0.23`) conflict — resolve the dependency story
   (separate env / drop codebleu / vendor) before this lands in the SDK proper.

**Risk called out honestly:** the value-add over today's regex security checks is
*real taint*, and real taint is precisely the part TraceQL does **not** give us for
free. The spike de-risks the pipeline and the coarse filter; it does **not**
de-risk flow-sensitive dataflow extraction, which is where Phase 2/3 effort and
uncertainty actually concentrate.
