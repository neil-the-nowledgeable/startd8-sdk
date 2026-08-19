# Business-context enrichment — high-level summary

**What this is:** how ContextCore business context (criticality, owner, SLOs, flow) reaches telemetry, so
observability + RCA answer *business* questions ("which revenue-primary flows failed?"), not just technical ones
("service X is down"). Two origination mechanisms — one **static** (shipped), one **dynamic** (planned) — feed the
same `business.*` attribute namespace.

> **Classical instrumentation vs business instrumentation — two axes.** **Classical (technical)
> instrumentation** = *source-side signal generation* (code, auto-instrumentation, or **eBPF** that
> emits telemetry that didn't exist before). This approach's second axis is **business
> instrumentation** — making the *business dimension* observable by projecting **declared** business
> meaning (criticality, flow, value) onto the telemetry classical instrumentation already emits (the
> collector-side **enrichment** here), so business questions become answerable. **The coverage RCA is
> the proof.** The honest caveat: business instrumentation is **not** source-side signal generation —
> **declared, not discovered**, and it **rides on** classical instrumentation's base signal. We don't
> redefine instrumentation; business instrumentation is a distinct axis added alongside it.

## The two halves

| Half | Mechanism | Scope | Status | Answers |
|---|---|---|---|---|
| **STATIC** | **K8s pod annotations** (`contextcore.io/*`) → OTel **resource attributes** (`detector.py`) | per-pod / per-service, set once at process start | ✅ shipped | *what static business context does this service carry* |
| **DYNAMIC** | **OTel baggage** — seeded at a trusted entry → propagated per-request → materialized per-span | per-request / per-flow | 📄 planned | *which business FLOW is this request serving* |

Together they realize the **three-axis criticality model**: `service.business.criticality` (static, resource /
annotation / `build_criticality_map`) · `project.business.criticality` (fallback) · **`flow.business.criticality`**
(dynamic, baggage). Distinct axes — do not collapse.

## The pipeline (originate → propagate → materialize → policy)

```
ORIGINATE   static: contextcore.io/* pod annotations → resource attrs  (detector.py, shipped)
            dynamic: seed business baggage at a trusted entry           (planned)
PROPAGATE   baggage propagator carries the dynamic half every hop       (planned; absent in the SDK today)
MATERIALIZE resource attrs (static) + BaggageSpanProcessor (dynamic) → every span carries business.*  (planned, per-language via instrumentation-gen)
POLICY      OTTL in the collector routes / tail-samples / tiers by business.criticality               (planned; ContextCore)
```

## The payoffs

- **Flow-aware RCA** — dark-service-on-critical-flows prioritization; business-impact blast radius; journey-step attribution.
- **Per-flow cost/value sink tiering** — premium egress sink for checkout-flow traces, cheap/sampled for browse (same services), via the Phase-2 delivery router over `telemetry_sink.py`.
- **Vendor-neutrality** — the annotation map already targets standard OTel semconv (env → Datadog/Splunk/Grafana equivalents); baggage uses standard W3C baggage.

## Ownership

- **startd8-sdk** — baggage propagator + `BaggageSpanProcessor` + trusted-entry seeding; per-language materialization generated via `scaffold_codegen/instrumentation_gen.py`.
- **ContextCore** — the annotation detector (shipped, `detector.py`); the OTTL policy; flow-aware RCA (`coverage_rca`/`remediation`); the sink filter (Phase-2 delivery router).

## The single-source mandate (load-bearing)

`business.criticality` now has **several authoring homes** — the ContextCore manifest (`spec.business.criticality`),
`spec.targets[].criticality`, the **K8s pod annotation** (`contextcore.io/criticality`), and the **baggage seed** —
plus several *consumers* (DerivationRule, OTTL, the sink filter, RCA, the baggage seed). **Author it once and share
it.** The criticality-authoring lint (`ContextCore/HANDOFF_criticality-authoring-lint.md`) guards this — and its
blast radius now includes the pod annotation as a third static authoring home.

## Detailed docs

- `DESIGN_baggage-flow-criticality-rca.md` — the full baggage design note + cross-repo handoff (originate/propagate/materialize/OTTL/sink-filter/RCA, phases P0–P5, guardrails).
- `REFERENCE_contextcore-annotation-context-detection.md` — how ContextCore uses/enables K8s annotations for context detection (the static half).
- Cross-repo handoffs (in ContextCore): `HANDOFF_flow-criticality-baggage-rca.md`, `HANDOFF_criticality-authoring-lint.md`.
