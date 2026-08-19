# Design note: which `business.*` dimensions to ship around `business.flow` (reflective-instantiation)

**Date:** 2026-08-19 · **Type:** design note (reflective-instantiation / Mendeleev) · **Status:** proposal
**Method:** `/reflective-instantiation` — name the product space, census the empty cells, adjudicate each.
**Relates:** `DESIGN_baggage-flow-criticality-rca.md` (the carrier) · `../contextcore-intro/REFERENCE_business-instrumentation-in-the-otel-model.md` (the `business.*` semconv namespace) · the three-axis criticality model

---

## 0. The Mendeleev insight (why this note exists)

**`business.flow` isn't a lone new attribute — it opens the *dynamic column* of the `business.*` product space.**
The value isn't "flow"; it's the **carrier** (seed → propagate → materialize) that flow requires, which then makes
the *whole* dynamic column cheap to populate. So we aren't shipping a dimension — we're shipping the **dynamic
business-context axis**, with `{flow, criticality}` as its first, jointly-seeded members. Build the carrier once;
populate the column on demand.

## 1. The product space

`business.* dimension = MEANING-TYPE × GRANULARITY`. Invariant: *declared business meaning projected onto
telemetry*, carried by **Resource** (static, per-service) or **Baggage** (dynamic, per-request).

| Meaning-type | STATIC (Resource) | DYNAMIC (Baggage) |
|---|---|---|
| criticality | ✅ `business.criticality` (shipped) | 📄 flow-scoped criticality (this) |
| journey | — (n/a static) | 📄 **`business.flow`** (the anchor) |
| value / tier | ✅ `business.value` | ⬜ `business.tier` |
| ownership | ✅ `business.owner` | — (service property, not per-request) |
| cost | ✅ `business.cost_center` | — (static) |
| customer | — | ⬜ `business.customer_tier` |
| channel | — | ⬜ `business.channel` |
| tenant | (via tenancy) | ⬜ `business.tenant_tier` |

The **static column is shipped** (`detector.py`). This note is about the **dynamic column**.

## 2. Adjudication

| Dimension | Verdict | Rationale |
|---|---|---|
| **flow-scoped `criticality`** | **SHIP WITH `business.flow`** | Seeded from the *same* `route→flow→criticality` mapping; declaring the flow declares its criticality. It's what makes flow *actionable* (flow = which journey; criticality = how much it matters). **Never ship `business.flow` without it.** |
| `business.tier` | earned-in | Ship only if per-flow **cost tiering** needs a key distinct from operational criticality; else fold into criticality (over-abstraction guard). |
| `business.channel` | natural-next, soon-after | Web/mobile/api — seeded at entry, low-cardinality, valuable; earn-in on a channel-scoped SLO/RCA need. |
| `business.tenant_tier` | natural-next, soon-after | Multi-tenant deployments (incl. ContextCore's own); tenant-scoped RCA/fairness. Ship the *tier*, not the id. |
| `business.customer_id` / `value_amount` / `revenue` | **correct-absence for baggage → ship as Events** | High-cardinality and/or PII/sensitive → belong on the **Events** signal, NOT propagated baggage (cardinality + trust/privacy on the wire). *Revealing-absence:* the baggage carrier is for LOW-cardinality, NON-sensitive dims. |
| `business.journey_step` | **revealing-absence (needs a seam)** | Baggage tags a request's *role*; it can't stitch a multi-request journey (add-to-cart → view-cart → place-order). Needs a **journey/session-ID** mechanism first. Defer. |
| `business.experiment` / `variant` | correct-absence | Couples to feature-flag infra; no demand yet. |

## 3. The minimal viable set

**Ship `{business.flow, business.criticality(dynamic)}` together** — one seed (`route→flow→criticality`), maximal
value. Everything else earns its seed on a named use case.

## 4. Two load-bearing disciplines

1. **Over-abstraction guard.** Do NOT populate the table because it's symmetric. Every baggage dimension costs
   header-bytes-per-hop + trust-surface + cardinality. `{flow, criticality}` first; each addition earns in.
   Symmetry-worship (8 dims "because the namespace should have them") is the anti-pattern; the baggage note's
   minimalism guardrail is the enforcement.
2. **A naming collision to resolve (semconv design).** Dynamic (flow) criticality and static (service) criticality
   are the *same* attribute name at two granularities — on one span you could carry both. **Give the dynamic one a
   distinct name**: the flow carries `business.flow`, and its criticality is **`business.flow.criticality`** (not a
   bare `business.criticality` colliding with the resource-level one). This is the three-axis *"don't collapse
   service into flow"* discipline, surfacing as a semantic-conventions decision — and it's an input to the proposed
   `business.*` semconv namespace.

## 5. Maturity

Static `business.*` (criticality/value/owner/cost_center) = **shipped** (`detector.py` + `transform/business`
OTTL). The dynamic column (`flow`, flow-criticality, tier, channel, tenant_tier) = **roadmap** (rides the baggage
carrier from `DESIGN_baggage-flow-criticality-rca.md`, P1–P2). This note is the co-ship spec for that column, and
is ready to promote to a formal REQ via `/reflective-requirements` (there is no `business.flow` REQ in either repo
today — only these design notes).

**One-line:** *ship the dynamic axis, not a single dimension — and `{flow, criticality}` are one seed, so they ship
together or not at all.*
