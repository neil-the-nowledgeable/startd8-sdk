# Design note: extending ContextCore RCA — flow-scoped fault isolation via business instrumentation

**Date:** 2026-08-19 · **Type:** design note (RCA extension) · **Status:** trajectory + mechanism on record
**Relates:** `DESIGN_baggage-flow-criticality-rca.md` (the baggage/flow-criticality substrate) · ContextCore
`coverage/*` (shipped coverage RCA), `utils/instrumentation.py` (the `transform/business` OTTL processor +
instrumentation-hint derivation) · the "business instrumentation" framing in `../contextcore-intro/`

---

## 0. The trajectory: coverage RCA → fault-isolation RCA

ContextCore's RCA today is largely **coverage RCA** (shipped): *are our critical services observable?* — find the
dark spots and rank them by business criticality (via the shipped `business_criticality` enrichment +
`coverage_rca`/`remediation`). **Business instrumentation's flow dimension extends this toward fault-isolation
RCA** (mostly roadmap): once a critical service *is* observable, isolate *which component / edge / change* caused
the failure — business-weighted and flow-scoped. Same enrichment layer, extended.

Honest framing throughout (consistent with the doc set): this enrichment **derives, correlates, prioritizes, and
discriminates** on the signal you already emit. It is **declared, not discovered** — it rides on classically-
instrumented base signal and cannot conjure a raw observation nobody emitted.

## 1. Seven OTTL enrichment levers for technical RCA

| # | Lever | RCA value | Axis |
|---|---|---|---|
| 1 | **Flow-scoped fault discrimination** (§2) | isolates a fault to the flow-specific path, not "the service is sick" | **business instrumentation (unique)** |
| 2 | Derive the service dependency graph + per-edge error/latency (spanmetrics/servicegraph) | find the *failing edge* | generic OTTL, *ranked by flow criticality* |
| 3 | Normalize/classify errors (status → semantic `error.category`) | group symptoms | generic OTTL |
| 4 | Inject correlation keys (version, pod, flow) onto traces/metrics/logs | pivot all three for the same slice | both |
| 5 | Stamp change/provenance (deploy version, `design.adr`) | answer *"what changed?"* | generic OTTL |
| 6 | Derive SLO-breach flags from the *business* SLO | RCA starts from business-defined "bad" | **business instrumentation** |
| 7 | Coverage-gap detection (expected-vs-emitted, `instrumentation.py`) | RCA of the blind spots — "it's dark; instrument it" | ContextCore's shipped coverage RCA |

Rows 2–5 are things any good OTTL setup can do. **The value unique to business instrumentation is #1 (and #6).**

## 2. The flow tag as a causal discriminator (the heart)

### The mechanism
`productcatalogservice` is called by two flows — **browse** (frontend → `ListProducts`) and **checkout**
(checkoutservice → `GetProduct` per cart item, during `PlaceOrder`). At the trusted entry each request is tagged
`business.flow=checkout|browse` in baggage; it propagates the whole way; the `BaggageSpanProcessor` materializes
it onto **every** productcatalog span. Group the service's errors by that tag:

```
productcatalog errors WHERE flow=checkout → 25%
productcatalog errors WHERE flow=browse   → 0%
```

Same service, split by the flow it served. That is the discrimination.

### Why the normal view hides it — de-blending
Without the tag, productcatalog's error rate is a **blend** across callers. If checkout is 25% errors on 20% of
traffic and browse is 0% on 80%, the service-level rate is ~5% — reads as *"slightly degraded,"* not *"the checkout
path is broken."* Healthy browse traffic **dilutes** the signal. The flow tag is a group-by dimension that
**un-blends** the mixed population.

### Why "checkout-only" points at a root cause
The two flows exercise **different internals** — browse hits (often-cached) `ListProducts`; checkout hits
`GetProduct` per cart item. Checkout-only failure ⇒ the fault is in what checkout does *differently*: that specific
RPC, a downstream dep only that path calls, or a code branch only cart-driven inputs hit. It collapses the search
from *"the whole service"* to *"the checkout-specific sub-behavior"* (e.g. "a deploy broke `GetProduct` for one
category; `ListProducts` is fine").

### The deep reason it beats pure technical telemetry — intent is end-to-end, technical attributes are local
"Just group by RPC method" sometimes suffices. The flow tag is *uniquely* valuable in two cases:
1. **Multiplexing** — the *same* operation serves multiple business intents (`GetProduct` called by both checkout
   AND a product-detail page). Method-grouping blurs them; flow-grouping separates them.
2. **Depth** — several hops down, a generic infra span (`redis GET`, `currency.Convert`) has *lost* all business
   context; its local attributes can't say which journey it served. **The flow tag is the only thing carrying
   end-to-end business intent that deep** — so a failing redis call four hops in *knows* it's on a revenue-critical
   checkout journey. You cannot reconstruct that from the redis span alone.

**The crux:** technical attributes are *local*; the flow tag propagates business *intent* across every boundary —
which is exactly what lets RCA attribute a deep, generic failure to the checkout journey when nothing local could.

### Second-order value
- **Blast-radius by flow** — "affects checkout (critical), not browse (low)" → clear business impact + prioritization.
- **Originated vs propagated** — dependency graph + flow tag together isolate whether productcatalog's checkout
  errors originate in it or in a downstream dep only the checkout path calls (never charge the entry orchestrator
  for a downstream break).
- **Coherent cross-signal picture** — slice logs + metrics + traces by `flow=checkout`; the error logs, the latency
  spike, and the failing traces all filter to one population.

## 3. Honest boundaries

- **Declared, not discovered** — the tag tells you *which* journey; you still investigate *why* within it. It
  narrows, it doesn't diagnose.
- **Propagation fragility** — a hop that drops baggage loses the tag downstream (the polyglot chain caveat).
- **Seeding correctness** — a wrong route→flow mapping gives wrong discrimination (single-source the mapping; it's
  guarded by the same criticality-authoring discipline).
- **Prepares, doesn't reason** — cross-record correlation / anomaly / causal isolation is the downstream RCA engine
  (`coverage_rca`/`remediation`); OTTL enriches and structures so that engine is faster and business-aware.
- **Cardinality** — `flow` is low-cardinality (fine as a metric dimension); de-blends cleanly on traces/logs
  (per-record); never add request-id to metrics.

## 4. How it extends ContextCore's RCA (maturity)

- **Shipped:** the `business_criticality` enrichment (`transform/business` OTTL processor) + coverage RCA
  (blind-spot detection ranked by criticality).
- **Roadmap:** flow-scoped propagation (baggage) + the fault-isolation levers above (dependency-graph derivation,
  error classification, change stamping, flow discrimination). This note is the design for that extension.

**One-line:** coverage RCA asks *"do we have the data?"*; business-instrumented fault-isolation RCA asks *"what
broke, on which valuable flow, because of what change?"* — and the flow tag is what carries the business intent
deep enough to answer it.
