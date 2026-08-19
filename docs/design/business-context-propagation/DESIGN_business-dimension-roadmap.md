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

**The MEANING-TYPE axis has three sub-axes: priority | attribution | obligation.** The original list
enumerated only *priority* types (criticality, value/tier) and *attribution* types (flow, channel, tenant,
customer) — it was blind to an **obligation/regulatory** sub-axis (*"what is owed here"*, e.g. compliance
scope). The three-sub-axis framing is now the spine of the table. **Over-abstraction guard:** the third
sub-axis (obligation) earns its place in the framing *only because* a concrete obligation dimension actually
lands (`business.compliance_scope`, below) — do not add sub-axes to complete a symmetry.

| Sub-axis | Meaning-type | STATIC (Resource) | DYNAMIC (Baggage) |
|---|---|---|---|
| **priority** | criticality | ✅ `business.criticality` (shipped) | 📄 flow-scoped criticality (this) |
| **priority** | value | ✅ `business.value` | ⬜ *(outcome — see below → Events)* |
| **attribution** | journey | — (n/a static) | 📄 **`business.flow`** (the anchor) |
| **attribution** | request-role | — | ⬜ `business.journey_step` (as-role — ship now; stitched-sequence deferred) |
| **attribution** | transaction | — | ⬜ `business.transaction_type` (folds into flow until a flow spans >1 op-class) |
| **attribution** | channel | — | ⬜ `business.channel` |
| **attribution** | entitlement | — | ⬜ `business.customer_tier` / `business.tenant_tier` (one meaning-type) |
| **obligation** | compliance | (data-classification, static) | ⬜ **`business.compliance_scope`** (PCI/GDPR/HIPAA) — strongest missing dynamic dim |
| priority | tier | *(likely folds into criticality — see §2)* | — |
| attribution | ownership | ✅ `business.owner` | — (service property, not per-request) |
| priority | cost | ✅ `business.cost_center` | — (static) |
| priority | *(derived)* | — | *`sla_tier` = entitlement × criticality — a policy output, not its own dim* |

The **static column is shipped** (`detector.py`). This note is about the **dynamic column**.

## 2. Adjudication

| Dimension | Verdict | Rationale |
|---|---|---|
| **flow-scoped `criticality`** | **SHIP WITH `business.flow`** | Seeded from the *same* `route→flow→criticality` mapping; declaring the flow declares its criticality. It's what makes flow *actionable* (flow = which journey; criticality = how much it matters). **Never ship `business.flow` without it.** |
| **`business.compliance_scope`** (PCI/GDPR/HIPAA) | **STRONGEST MISSING DYNAMIC DIM — obligation sub-axis** | Low-cardinality, non-PII, trusted-entry-seeded; drives sink routing **exactly like criticality** — but answers *"what is owed here"* (obligation), not *"how much it matters"* (priority). Passes the **same** low-cardinality / non-PII / trusted-seed filter this roadmap already built (convergence signal — it earns in through the existing gate, not a new one). **Sharper edge:** mislabeling scope has a *legal* blast radius, so the trusted-entry-seed guardrail is load-bearing here (not merely hygienic). **Ceiling-raiser (angle B, flagged as later scope only):** compliance/data-classification is where the machinery converts from an *analytics dimension* into an *enforcement control plane* — route/redact telemetry crossing a residency boundary. That enforcement ceiling is **out of scope for this note**; it ships as a dimension first. |
| `business.transaction_type` (read/write, checkout/refund/quote) | **natural-next dynamic dim — with a fold caveat** | Seeded at entry, low-cardinality. **Honest caveat:** in simple apps it **folds into flow** (a `checkout` flow *is* a checkout transaction) — it earns in **only when one flow spans multiple operation-classes** (e.g. a `wallet` flow carrying both reads and writes that must be distinguished for RCA/routing). |
| `business.journey_step` | **SPLIT verdict** | Ship **journey_step-as-request-role now**: same entry seed as flow (a request's role in a journey), overlaps `transaction_type`, no new seam. **Defer only journey_step-as-stitched-sequence** (add-to-cart → view-cart → place-order), which needs the **journey/session-ID** seam. The previous "defer the whole thing" verdict conflated the two. |
| `business.tier` | **likely-fold-into-criticality** *(was: earned-in)* | Re-classified. Revenue-primary tier ≈ critical criticality — the **same declared judgment** viewed twice. Do not ship a parallel key. **Resurrect only if a cost model prices tiers independently** of operational criticality (the one condition that makes them distinct). |
| `business.customer_tier` / `business.tenant_tier` | **consolidate under `entitlement` meaning-type** | Both express *what an entity is entitled to* — one recognized **entitlement** meaning-type, not two ad-hoc dims. Multi-tenant / customer-scoped RCA/fairness. Ship the *tier*, not the id. |
| `sla_tier` | **NOT its own dim — a derived policy output** | `sla_tier` = **entitlement × criticality**, computed downstream — a policy output, not a propagated dimension. **Resist symmetry-worship:** do not mint a baggage key for every noun the namespace suggests. |
| `business.customer_id` / `value_amount` / `revenue` | **ship as Events — because they're OUTCOMES, not declared intent** | **Primary reason (intent-dimension vs outcome-measurement):** baggage carries *declared intent* about a request's role; `customer_id`/`value`/`revenue` are *outcomes measured after the fact*, which belong on the **Events** signal — a category difference, not just a hygiene one. **Secondary:** they are also high-cardinality and/or PII/sensitive, so the cardinality + trust/privacy-on-the-wire guardrails independently exclude them from propagated baggage. |
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
