# Synthesis: divergent-agent analysis of business instrumentation (5 blind angles)

**Date:** 2026-08-19 · **Type:** synthesis of `ANALYSIS_KIT_re-analyze-business-instrumentation.md` runs
**Method:** 5 agents, one angle each, blind (no peeking), grounded in the corpus. Convergence = what ≥2 independently
surfaced (high signal). Divergence = the sharpest single-angle finding. Over-abstraction guard applied throughout.
**Angles run:** F (adversarial refutation) · C (adjacent-domain analogy) · B (deeper abstraction) · G (non-baggage
carriers) · A (instantiation redux).

---

## 0. The honesty meta-finding (before the substance)

Multiple angles independently noted their attacks **landed on the corpus's own stated caveats** — "declared, not
discovered," "the moat is the discipline not the mechanism," the trust-boundary and cardinality guardrails. An
adversarial pass that hits exactly the documented fault lines is signal the corpus is **honestly scoped, not
hand-wavy.** The improvements below extend it; they don't catch it hiding anything.

## 1. Convergences (ranked — what ≥2 angles independently surfaced)

### C1 — The "single-source map" is not a table to lint; it's a governed REGISTRY / decision point to build. *(F, C, B — 3 angles)*
The strongest convergence. The `route→flow→criticality` map (REQ FR-1, baggage §7) is under-built as a linted
static table:
- **C (FinOps + zero-trust + product analytics, 3 sub-domains):** the declared vocabulary needs a governed,
  *versioned, enforced* registry — allowed-values enum, **coverage %** ("what fraction of live traffic carries a
  mapped flow?"), an **unmapped bucket** (the honest denominator), and a **lifecycle** (draft→active→deprecated).
  Zero-trust's OPA answers the corpus's *exact* §7 drift fear with an externalized **PDP the consumers query**, not
  a table they each copy.
- **B:** the §7 "one criticality feeds five consumers" is a **star-schema join**; the load-bearing artifact is a
  **registry** (declared-table × join-key × stage × consumers), not the `BaggageSpanProcessor`. *This vindicates and
  sharpens the moat thesis — the moat IS the join registry.*
- **F:** the map **rots** (the CMDB/tag/flag-debt problem); the defensible thing is *keeping it from rotting* (a
  continuous-verification loop), not the one-time declaration.

**Metabolize:** promote §7's map to a governed **business-context registry** (allowed-values, coverage %, unmapped
bucket, lifecycle). **Earned-in guard:** externalize to a full PDP only at ≥2 declared tables or on real observed
drift — at one table (business.*) the lint is correct.

### C2 — The map's FIDELITY (not just consistency) is unguarded — the highest-*severity* finding. *(F, C, B — 3 angles)*
- **F (the sharpest single finding of the whole run):** the headline **de-blending** (RCA-extension §2) runs
  **backwards** under a stale/wrong map — a mis-mapped route silently folds a critical-flow failure *into* the
  "healthy" bucket, making RCA **confidently wrong rather than merely absent.** FR-1 guards *consistency*, FR-6
  guards *reach* — **neither checks semantic fidelity.** This is the repo's own "verification that cannot silently
  die" bug reappearing one level up: a verified-propagated tag attesting the wrong thing.
- **C/B:** single-sourcing ≠ correctness; the fix is a **discovered-vs-declared reconciliation** (a join-conflict /
  drift oracle).

**Metabolize:** add a **map-fidelity oracle** — sample real traces, test-classify against the declared map, alarm on
divergence + route-coverage drift. **Honest tension:** this imports a *discovery* step the "declared-only" discipline
resists — so it must be framed as a drift *guard on* the declaration, not a replacement for it.

### C3 — The parent abstraction is bigger: "declarative context joins over telemetry." *(B, C — 2 angles, and the ceiling-raiser)*
- **B:** `detector.py` and `k8sattributes` already run the *same* join (declared-attrs ⋈ signal on the pod key) at two
  stages — "join on key" is the real primitive; "dimension" is just its output shape. The same machinery admits other
  authored tables (**org-chart/on-call, service-catalog/CMDB, cost model, SLO, compliance**) joining on
  service/route/flow keys. `business.*` is the **beachhead, not the ceiling.**
- **C:** four mature domains have already built the governance for exactly this control plane.

**Metabolize:** frame the roadmap's `MEANING-TYPE × GRANULARITY` as `(declared table) × (join key)`; keep `business.*`
as the shipping beachhead. **Earned-in guard (load-bearing):** generalize the **contract/registry** now (cheap —
mostly renaming existing artifacts); **defer any generic join *engine* until table #2 is wired** (a framework for a
single use is the accidental complexity the corpus forbids).

### C4 — Compliance/obligation is the missing meaning-type — and it raises the ceiling from analytics to ENFORCEMENT. *(A, B, C — 3 angles)*
- **A:** `business.compliance_scope` (PCI/GDPR/HIPAA) is the strongest *un-listed* dynamic dimension — low-cardinality,
  non-PII, trusted-entry-seeded, drives sink routing exactly like criticality, but answers *"what is owed here."* The
  meaning-type axis is **blind to an entire "obligation" row.**
- **B:** compliance/data-classification is where the join framing **beats business-instrumentation outright** — it
  converts the machinery from an *analytics dimension* into an *enforcement control plane* (drop/route/redact
  telemetry crossing a residency boundary).
- **C:** zero-trust data-classification labels are the same policy-carrying pattern.

**Metabolize:** add `business.compliance_scope` + an "obligation" meaning-type; recognize the **enforcement** ceiling
(the mesh/OTTL seam is a policy *decision/enforcement* point, not only an enrichment point).

### C5 — Baggage isn't the only carrier: a HYBRID (baggage=real-time, trace-derivation=analysis) is the honest design. *(G primary, F reinforces)*
- **G:** `business.flow` is **recoverable post-hoc from the assembled trace's root span** (which already carries the
  entry route) — a collector-side pass stamps it *down* with **zero baggage propagation.** Baggage is *strictly
  necessary only* for the **real-time-at-ingest** levers (tail-sample retention, the §4b premium-sink cost tiering,
  live P1 alerting). For the **analysis/RCA** segment — the corpus's own strongest payoff — trace-derivation
  dominates on brownfield/polyglot/async fleets ($0 rollout). FR-6 (propagation-coverage) is **baggage-path-only.**
- **F:** baggage **structurally breaks** across async/queue/batch/serverless/third-party hops — reinforcing that
  baggage-everywhere is fragile.

**Metabolize:** adopt the **hybrid** — baggage for real-time, trace-derivation for analysis, session-ID+join for the
deferred `journey_step` — all reading the *one* declared map (extend §7 to cover the derivation consumer). Brownfield
shops get ~80% of the RCA value with no propagator rollout.

## 2. Sharpest single-angle divergences (the unique killers)

- **F:** de-blending runs **backwards** under a wrong map → *confidently-wrong* RCA the corpus's own guards can't
  detect (C2 above — the highest-severity finding).
- **C:** the corpus fears the **exact drift OPA's PDP/PEP was invented to solve**, but stops one maturity rung short.
- **B:** **compliance-as-enforcement** raises the product ceiling; the general capability is a governed control plane
  that joins *any* authored table onto telemetry (business + cost + owner + compliance).
- **G:** baggage is **not necessary for the analysis use case** — trace-derivation from the root span.
- **A:** the **meaning-type axis is incomplete** — priority + attribution present, **obligation missing**; also fold
  `tier` into criticality, ship `journey_step`-as-role now (defer only the stitched sequence), and make
  intent-dimension-vs-outcome-event the *primary* reason value/revenue go to Events.

## 3. The metabolization backlog (prioritized, with the honest guard on each)

| # | Change | From angles | Effort | Earned-in guard |
|---|--------|-------------|--------|-----------------|
| 1 | **Map → governed business-context registry** (allowed-values, coverage %, unmapped bucket, lifecycle) | F, C, B | M | full PDP only at ≥2 tables / real drift; lint fine at 1 |
| 2 | **Map-fidelity/drift oracle** (discovered-vs-declared reconciliation) — closes "confidently wrong" | F, C, B | M | frame as a drift *guard*, not a replacement for declaration |
| 3 | **Reframe: declarative context joins over telemetry**; `business.*` = beachhead; moat = join registry | B, C | S (framing) / L (product) | generalize the *registry* now; defer the generic *engine* to table #2 |
| 4 | **`business.compliance_scope` + "obligation" meaning-type + the enforcement ceiling** | A, B, C | S (dim) | trusted-entry seed is legally load-bearing here |
| 5 | **Hybrid carrier** (baggage=real-time, trace-derivation=analysis); FR-6 = baggage-path-only | G, F | M | two carriers = a 6th consumer of the one map (drift surface) |
| 6 | **Governance hardening:** intra-mesh "propagate-but-not-author" tag authority + flow-cardinality budget + attested/audited seed | F, C | S–M | closes the internal cost-abuse + value-cardinality gaps |
| 7 | **Roadmap taxonomy fixes:** 3 sub-axes (priority/attribution/obligation); fold `tier`→criticality; ship `journey_step`-as-role now | A | S | each sub-axis earns in on a real use case |

## 4. The one-line synthesis

*The divergent pass validated the corpus's honesty (attacks hit the stated caveats) and converged on one big move:
the defensible artifact isn't the baggage dimension — it's the **governed, fidelity-checked business-context registry**
(a join/decision control plane), of which `business.flow` RCA, per-flow cost, and compliance-boundary enforcement are
instances; ship `business.*` as the beachhead over a hybrid (baggage + trace-derivation) carrier, and the moat thesis
gets sharper, not weaker — the moat is the registry and the maintenance loop, not the propagation mechanism.*
