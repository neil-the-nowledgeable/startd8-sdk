# Analysis kit: re-derive "business instrumentation" independently (a prompt for divergent agents)

**Date:** 2026-08-19 · **Type:** analysis kit / reflective prompt · **Purpose:** let *other* agents analyze the
same corpus along the same (or deliberately different) lines to surface patterns, dimensions, and refutations a
single reasoning line missed. **This is a DIVERGENCE tool, not a confirmation one** — a run that only agrees with
the corpus has failed. Correct-absence and refutation are valid, valuable results.

---

## 0. How to use this

Pick one or more **angles** (§3), read the **corpus** (§1) and the **method** (§2), obey the **guardrails** (§4),
and return the **structured findings** (§5). Ideal as a fan-out: several agents, one angle each, run independently
(no peeking at each other), then a synthesis pass looks for what ≥2 independently surfaced (convergence ⇒ signal).

## 1. What we built (the corpus — read before analyzing)

**The idea:** *business instrumentation* — making the *business dimension* of a system observable by projecting
**declared** business meaning (criticality, flow, value, owner) onto the telemetry classical instrumentation
already emits. A distinct discipline from classical (source-side signal-generating) instrumentation; it *rides on*
it; its information is **declared, not discovered**.

**The artifacts** (all under `startd8-sdk/docs/design/`):

| File | What it holds |
|------|---------------|
| `business-context-propagation/DESIGN_baggage-flow-criticality-rca.md` | the carrier: originate→propagate→materialize→OTTL→sink-filter→RCA; the three criticality axes (service/project/flow); k8s-declarative materialization; guardrails |
| `business-context-propagation/DESIGN_rca-extension-flow-fault-isolation.md` | coverage-RCA→fault-isolation-RCA; 7 enrichment levers; the flow tag as causal discriminator (de-blending; intent-is-end-to-end) |
| `business-context-propagation/DESIGN_business-dimension-roadmap.md` | reflective-instantiation of the `business.*` space; the `{flow, criticality}` co-ship; over-abstraction guard; the naming-collision fix |
| `business-context-propagation/REFERENCE_contextcore-annotation-context-detection.md` | the shipped static half (`contextcore.io/*` pod annotations → resource attrs, `detector.py`) |
| `business-context-propagation/REQ-business-flow-and-flow-criticality.md` | the formal REQ (det-req/0.1) for the dynamic axis |
| `contextcore-intro/REFERENCE_business-instrumentation-in-the-otel-model.md` | how it fits OTel (a dimension, not a signal); the absent `business.*` semconv namespace; `business.flow` creation; the competitive landscape |
| `contextcore-intro/{01..05, LINKEDIN, EMAIL}` | the audience-tiered intro set (ELI5→GTM) + the "two axes" framing + the coined term |
| `EXECUTIVE_contextcore-capabilities-overview.md` | the broader ContextCore capability context |

**Grounded facts to respect:** the static axis (`business.criticality` via `detector.py` + the `transform/business`
OTTL processor, consumed by coverage RCA) is **shipped**; the dynamic axis (`business.flow`, baggage) is
**roadmap**. The plumbing (Operator, `k8sattributes`, OTTL, mesh, baggage) is **open/commoditized** — the moat is
the governed control plane, not the mechanism.

## 2. The method/lens we used (replicate — or deliberately diverge from it)

- **Reflective tools:** `/reflective-instantiation` (Mendeleev — census the empty cells of a named space),
  `/reflective-abstraction` (variants→algebra), `/reflective-analogy` (a solved domain→this one).
- **Honest-grounding discipline:** declared-vs-discovered; shipped-vs-roadmap marked; no over-claiming; the moat is
  the discipline, not the mechanism.
- **Over-abstraction guard:** don't populate a namespace because it's symmetric; each dimension earns its seed.
- **Narrow-waist framing:** OTel is the telemetry waist; business context rides it as an attribute dimension.

**To diverge on purpose:** an agent that *rejects* one of these lenses (e.g., "stop treating it as a dimension —
model it as X") may surface the most.

## 3. Analytical angles (pick one; each is self-contained)

**A. Reflective-instantiation redux — other `business.*` dimensions.** Re-census the space independently. Did we
miss dynamic dims (region/geo, compliance-scope PCI/GDPR, sla-tier, partner, workflow-stage, channel) or *static*
ones (team, product, domain)? Adjudicate each natural-next / earned-in / correct-absence. Don't just agree with
`DESIGN_business-dimension-roadmap.md` — find what it left out or over-included.

**B. Reflective-abstraction — the deeper invariant.** We called it "declared meaning projected onto telemetry." Is
there a *stronger* algebra? Candidate to test: **business instrumentation = a JOIN between a declared knowledge
graph and the runtime telemetry graph.** If so, what *other* declared graphs could join (org chart, service
catalog/CMDB, cost model, ownership/on-call)? Does that reframe reveal patterns the "dimension" framing hides?

**C. Reflective-analogy — adjacent domains that propagate declared context.** Map patterns from: **FinOps cost
tagging** (allocation/showback/chargeback → per-flow cost), **security context propagation** (SPIFFE/SPIRE
identity, zero-trust labels, data-classification riding requests — `business.flow` behaves like a *policy-carrying
label*), **data lineage/provenance**, **feature-flag/experiment context**, **product-analytics funnels**. What
transfers? (e.g., borrow a *policy engine* from zero-trust, or *showback* from FinOps.)

**D. The OTel-model fit from other angles.** We argued "dimension, not signal, riding Resource + Baggage." Probe:
**Events** (business events as the high-cardinality complement to low-cardinality baggage dims — is this a stronger
home for value/revenue?), **Profiles** (flow-scoped profiling), **Exemplars** (link metrics→traces carrying
business context), **Span Links** (correlate across journeys). Does one of these deserve first-class treatment we
under-weighted?

**E. RCA levers beyond flow-discrimination.** `DESIGN_rca-extension-*` lists 7. Find more: deploy/change
correlation, business-load-vs-saturation correlation, error-budget-burn attribution by flow, flow-scoped anomaly
detection, blast-radius simulation. Which are unique to business instrumentation vs generic OTTL?

**F. Adversarial refutation (the most valuable if done honestly).** Try to *break* it: what if flows aren't
route-discriminable (messy enterprise routing)? what if the org won't declare the mapping (change-management
cost)? where does baggage propagation fail in practice (polyglot gaps, async/queues, batch)? how fast could an
incumbent copy it? Where is the honest-limit ("declared, not discovered") most damaging? A strong refutation
*strengthens* the work.

**G. Other carriers — is baggage even necessary?** Probe alternatives: **derive `business.flow` from the trace
structure** (the root span carries the entry route; a collector-side pass could propagate it *down* the assembled
trace — avoiding baggage entirely, trading propagation-fragility for trace-assembly). Also: resource attrs, log
correlation, entity/graph joins. Does a non-baggage mechanism dominate for some cases?

**H. Structural inference (implicature audit on our own work).** What does the *structure* we built IMPLY that we
never stated? E.g., a single-source criticality map consumed by 5 things ⇒ the structure implies a **business-
context registry / control-plane API**, not just a map. Static + dynamic axes ⇒ a **reconciliation** concern when
they disagree. Surface the forced-but-unstated consequences.

## 4. Guardrails (the discipline — a finding that violates these is noise)

- **Correct-absence is a valid result.** "We should NOT add X" is as useful as "add X." Resist symmetry-worship.
- **Declared, not discovered.** Anything you propose must respect that business meaning is authored, not inferred
  from the system; if it requires discovery, say so (it's a different mechanism).
- **Honest maturity.** Mark shipped vs roadmap vs upstream-maturing. Do not present the roadmap as done.
- **The moat is the discipline, not the mechanism.** Don't propose a "differentiator" that's just open plumbing
  anyone can assemble; if it's DIY-able, say so and locate the real defensibility (governance/control-plane).
- **Ground every claim in the corpus or a real external practice** (name the FinOps/security/OTel prior art).

## 5. What to return (structured, so findings can be metabolized)

For each finding:

```
- kind: new-dimension | new-lever | new-carrier | reframe | refutation | structural-implication | correct-absence
- claim: <one line>
- rationale/grounding: <why; cite the corpus file or the external prior art>
- where it plugs in: <which artifact/axis it extends, or which it refutes>
- maturity/effort: <shipped-adjacent | roadmap | needs-a-new-seam> · <XS/S/M/L>
- honest caveat: <the limit; what would make it wrong>
```

Close with a **one-line convergence note** if your angle independently re-derived something the corpus already has
(that's signal the corpus got it right) and a **one-line divergence note** (the single most surprising thing your
angle surfaced that the corpus missed).

---

**The point:** we produced one coherent line of reasoning about business instrumentation. This kit exists to test
it against *other* lines — to find the dimensions, carriers, analogies, and refutations a single analyst can't see.
Bring back what we missed, or prove a piece wrong; both make the work stronger.
