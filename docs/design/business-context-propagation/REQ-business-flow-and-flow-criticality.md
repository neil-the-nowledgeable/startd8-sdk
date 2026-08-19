# Ship the Dynamic Business-Context Axis (`business.flow` + `business.flow.criticality`) — Requirements

**Project:** ContextCore + startd8-sdk (cross-repo)   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-19
**Format:** det-req/0.1
**Backend:** otel-pipeline (k8s-declarative)
**Pairs with:** *(plan deferred — spec promoted from the design notes via /reflective-requirements)* · **`DESIGN_baggage-flow-criticality-rca.md`** (the carrier) · `DESIGN_business-dimension-roadmap.md` (the co-ship adjudication) · `DESIGN_rca-extension-flow-fault-isolation.md` (the consumer) · `../contextcore-intro/REFERENCE_business-instrumentation-in-the-otel-model.md` (the `business.*` semconv namespace)
**Inherits standards:** OTel semantic conventions · W3C Baggage · Context-Correctness-by-Construction · the criticality-authoring lint (single-source) · the minimalism/trust guardrails of the baggage design note
**Audience:** platform/SRE · ContextCore + SDK contributors
**Trust boundary:** business `business.*` baggage is set/overwritten ONLY at a trusted boundary; client-supplied `business.*` baggage is stripped; advisory/additive; byte-identical when the flow map is absent
**Data classification:** internal; low-cardinality, non-PII dimensions only

> **Readable handle:** `feature/dynamic-business-context-axis-flow-and-flow-criticality-34418f1a`
> **Semantic name:** *ContextCore and the SDK ship the dynamic business-context axis by declaring a single-sourced route-to-flow-to-criticality map, seeding `business.flow` and `business.flow.criticality` at a trusted mesh boundary, propagating them via the standard baggage propagator configured fleet-wide, materializing an allowlisted key set onto spans, verifying propagation reaches downstream spans, using a non-colliding attribute name, and staying additive and byte-identical when the flow map is absent, so a request carries its business journey and its weight end-to-end for flow-aware RCA and value tiering.*
> **Canonical ref:** `cc:intent:business-context:feature:business-flow`

## 0. Why this exists

The static business-context axis is shipped (`detector.py` annotations + the `transform/business` OTTL processor →
`business.criticality` per service). This REQ ships the **dynamic axis**: a request's **business journey** and its
**weight**, carried end-to-end so a failure attributes to *"a revenue-primary checkout,"* not *"server 7."* Per the
Mendeleev framing, `business.flow` opens the dynamic column of `business.*`; `{flow, criticality}` are its first,
**jointly-seeded** members. This spec was promoted from the design notes via `/reflective-requirements`; the
imagined-build discoveries are folded into the FRs/NRs below.

## Design decisions

- **`{flow, criticality}` are ONE seed.** The `route→flow→criticality` map declares both at once; flow without
  criticality is an unactionable label (FR-8). Ship together or not at all.
- **Declarative-first (k8s-derived).** Seed = a mesh header rule; propagate + materialize = the OTel Operator
  `Instrumentation` CRD. Code is the fallback, per the baggage note §2b.
- **Distinct naming.** `business.flow.criticality` (dynamic) must not collide with `business.criticality`
  (resource-level static) — the three-axis "don't collapse service into flow" discipline as a semconv decision.
- **Low-cardinality, non-sensitive only.** Flow/criticality are low-cardinality; high-cardinality/PII dims
  (customer_id/value/revenue) are OUT — they ship as Events, not baggage (NR-4).
- **Trust boundary = a cost/priority-abuse vector.** Seed only at a trusted boundary; strip client baggage (NR-5).

## Overview

Declare a single-sourced `route→flow→criticality` map; seed `business.flow` + `business.flow.criticality` at a
trusted boundary (mesh rule; entry hook for content-determined flows); propagate via the standard baggage
propagator configured fleet-wide; materialize an allowlisted `business.*` key set onto spans; verify the flow tag
reaches downstream spans (propagation-coverage); additive and byte-identical when the map is absent.

## Objectives

- **O-1:** A request carries its business journey + weight end-to-end — target: `business.flow` and `business.flow.criticality` appear on downstream spans across the call graph, derived from the declared map.
- **O-2:** The dynamic axis is governed, verifiable, non-colliding — target: the map is single-sourced (lint-guarded), propagation is coverage-checked, and the dynamic attribute name never collides with the static one.
- **O-3:** Safe and additive — target: trust-bounded (client baggage stripped), low-cardinality, byte-identical when the flow map is absent.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security | A client injects `business.flow`/criticality to buy priority or premium retention | FR-2/NR-5: seed only at a trusted boundary; strip/overwrite client-supplied `business.*` baggage | high |
| reliability | A service drops the baggage propagator → the flow tag silently vanishes downstream | FR-3 fleet-wide propagator + FR-6 propagation-coverage check (a dropped hop is a loud gap) | high |
| quality | Dynamic criticality collides with the resource-level `business.criticality` | FR-5: distinct name `business.flow.criticality` | high |
| performance | High-cardinality dims on baggage/metrics explode cost | NR-4 low-cardinality only; FR-7 flow on traces/logs, controlled on metrics | medium |
| scope | Re-specifying the shipped static axis or the consumer policies | NR-1/NR-3: dynamic axis only; RCA/tiering policies consume, not defined here | medium |

## Functional requirements

- **FR-1 — The flow map is a declared, single-sourced artifact.** A `route→flow→criticality` map is declared as a ContextCore CRD/config and is the single source of truth for the dynamic axis, drift-guarded by the criticality-authoring lint (extended to span the flow map alongside manifest and targets). Name: The route-to-flow-to-criticality map is a declared single-sourced artifact guarded against drift. Touches: `ContextCore/src/contextcore/coverage/criticality.py`, `ContextCore/HANDOFF_criticality-authoring-lint.md`, flow-map CRD/config. Lives: config ContextCore/flow-map. Approve?: is the flow map declared once and drift-guarded across its authoring homes?. Verify: a flow map authored in two places or conflicting with the manifest criticality is flagged by the lint; a single-sourced map passes. Serves: O-2

- **FR-2 — Seed at a trusted boundary; strip client baggage.** Seed `business.flow` and `business.flow.criticality` from the map at a trusted boundary — a mesh header rule for route-discriminable flows, an entry hook for content-determined ones — and strip or overwrite any client-supplied `business.*` baggage so it cannot be injected. Name: Business flow and its criticality are seeded only at a trusted boundary and client-supplied business baggage is stripped. Touches: mesh (Istio/Envoy) header rule, `startd8-sdk/src/startd8/otel.py`, entry hook. Lives: config mesh/business-flow-seed. Approve?: are the dimensions seeded only at a trusted boundary with client baggage stripped?. Verify: a client that sends `business.flow`/criticality in baggage has it overwritten or stripped at the boundary; the seeded value derives from the map, not the client. Serves: O-1, O-3

- **FR-3 — Propagate via the baggage propagator, fleet-wide.** The standard W3C baggage propagator is configured across the fleet (via the OTel Operator `Instrumentation` CRD, `OTEL_PROPAGATORS=tracecontext,baggage`) so the dimensions ride every hop; no custom propagator. Name: The baggage propagator is configured fleet-wide so the dimensions ride every hop. Touches: OTel Operator `Instrumentation` CRD, `startd8-sdk/src/startd8/otel.py`. Lives: config operator/Instrumentation. Approve?: is standard baggage propagation configured fleet-wide?. Verify: `business.flow` set at the entry is present in the baggage of a service several hops downstream; a service without the propagator is detectable. Serves: O-1

- **FR-4 — Materialize an allowlisted key set onto spans.** A `BaggageSpanProcessor` copies an ALLOWLISTED set of `business.*` baggage keys (`business.flow`, `business.flow.criticality`, …) onto spans — never all baggage — so the dimensions become queryable telemetry without leaking arbitrary context. Name: An allowlisted set of business baggage keys is materialized onto spans. Touches: OTel Operator `Instrumentation` CRD, `BaggageSpanProcessor` config. Lives: config operator/baggage-span-processor. Approve?: are only allowlisted business keys materialized onto spans?. Verify: `business.flow` appears as a span attribute downstream; a non-allowlisted baggage key does not appear on spans. Serves: O-1, O-3

- **FR-5 — Non-colliding attribute name.** The dynamic criticality is materialized as `business.flow.criticality`, distinct from the resource-level static `business.criticality`, so a span can carry both without ambiguity. Name: The dynamic criticality uses a distinct attribute name from the static resource-level one. Touches: the `business.*` semconv namespace proposal, `BaggageSpanProcessor` config. Lives: doc ../contextcore-intro/REFERENCE_business-instrumentation-in-the-otel-model.md. Approve?: does the dynamic criticality use a non-colliding name?. Verify: a span carrying a service-level `business.criticality` and a flow-level `business.flow.criticality` keeps them distinct and separately queryable. Serves: O-2

- **FR-6 — Propagation-coverage check.** A coverage/liveness probe verifies the flow tag actually reaches downstream spans across the call graph; a hop that drops it is surfaced as a loud gap (the propagation analogue of the coverage RCA). Name: A coverage probe verifies the flow tag reaches downstream spans and a dropped hop is a loud gap. Touches: `ContextCore/src/contextcore/coverage/`, a propagation-coverage check. Lives: code ContextCore/coverage/flow_propagation. Approve?: is flow-tag propagation coverage verified end-to-end?. Verify: a service missing the propagator yields a propagation-coverage gap for flows routed through it; a fully-propagating path yields none. Serves: O-2

- **FR-7 — Additive, low-cardinality, byte-identical when absent.** The dimensions are low-cardinality (flow on traces/logs; controlled on metrics), the whole path is additive, and when the flow map is absent nothing is seeded/materialized and telemetry is byte-identical. Name: The axis is additive low-cardinality and byte-identical when the flow map is absent. Touches: `BaggageSpanProcessor` config, tests. Lives: test ContextCore/coverage/tests/test_flow_axis.py. Approve?: is the axis additive low-cardinality and byte-identical when the map is absent?. Verify: with no flow map, no `business.flow` baggage or span attribute is produced and telemetry is byte-identical; flow is not emitted as an unbounded metric dimension. Serves: O-3

- **FR-8 — Flow and criticality co-ship from one seed.** `business.flow` and `business.flow.criticality` are seeded together from the single `route→flow→criticality` map — a flow is never seeded without its criticality. Name: Business flow and its criticality are seeded together from the one map. Touches: mesh header rule, flow-map CRD/config. Lives: config mesh/business-flow-seed. Approve?: are flow and its criticality always seeded together from the one map?. Verify: every span carrying `business.flow` also carries `business.flow.criticality`; a flow with no declared criticality is a map-authoring error, not a silent default. Serves: O-1, O-2

## Non-requirements

- **NR-1:** Does NOT re-specify the STATIC business context — `business.criticality`/owner/value/cost_center via `detector.py` + `transform/business` are shipped and out of scope. This is the dynamic axis only.
- **NR-2:** Does NOT stitch multi-request journeys — `business.flow` tags a request's role; multi-step journey correlation needs a journey/session-ID mechanism (a later REQ).
- **NR-3:** Does NOT define the consumer policies — flow-aware RCA (`DESIGN_rca-extension-flow-fault-isolation.md`) and per-flow cost tiering / the sink filter CONSUME this dimension; this REQ produces it.
- **NR-4:** Does NOT put high-cardinality/PII dims on baggage — `customer_id`/`value_amount`/`revenue` ship as Events, never as propagated baggage (cardinality + trust/privacy).
- **NR-5:** Does NOT trust client-supplied `business.*` baggage — it is stripped/overwritten at the trusted boundary.
- **NR-6:** Does NOT use a custom propagator — standard W3C baggage only.
