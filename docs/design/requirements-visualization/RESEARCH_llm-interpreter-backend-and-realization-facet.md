# Research note: expressing the LLM "interpreter" back-end in the Node IR, via a `realization` facet

**Date:** 2026-08-16 · **Type:** research / design consideration (emeritus) · **Status:** for discussion
**Frames:** the Natural-Language Programming System (`~/Documents/craft/THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md`)
**Relates:** `ADR_promote-oracle-and-human-gate-into-node-ir.md` (verify/approve) · `REQ-16` (derivation edge) ·
`NODE-SCHEMA.md` §1a (the three orthogonal axes / facets) · CLAUDE.md (the two generation paths)

## The question, split correctly

The NLPS is a compiler whose IR is the Node/contract, consumed by **two back-ends**: the deterministic
`$0` cascade (path 1 — the *compiler*, reproducible, Python-only) and the LLM-driven construction
(path 2 — the *interpreter/JIT*, polyglot, stochastic). "Is the LLM back-end expressible in the IR?"
is really two sub-questions, and keeping them apart is the whole discipline:

1. **Forward (routing/selection):** does the IR carry enough to *decide* which back-end realizes a node?
2. **Backward (provenance/realization):** does the IR *record* which back-end produced a node's realization?

These are the **same axis viewed in two directions.** The forward decider already exists off-IR
(`complexity/classifier.py:classify_tier` → TRIVIAL/SIMPLE/MODERATE/COMPLEX + the deterministic-provider
`$0`-skip hook). The backward record is exactly the proposed **`realization: deterministic | llm | human`**
facet. One facet closes both directions: it is the router's *output type* and the node's *provenance stamp*.

## Thesis (the load-bearing claim)

**The LLM back-end is expressible in the IR — but ONLY as a boundary-marker + a verification regime +
provenance. Never as back-end mechanics.** A real compiler IR is back-end-*neutral* (the same IR feeds
x86 or ARM); putting the back-end *into* the IR would destroy the pluggability that makes it an IR. So we
do not put the interpreter into the Node. We extend the Node to **type the reliability of each
realization**, so the two back-ends can be reasoned about uniformly. The `realization` facet is that type.

### Sharpening: it is not really "interpreter vs compiler" — it is **deterministic vs stochastic**

The thesis's interpreter/JIT metaphor is useful but imperfect: the LLM path produces *persistent
artifacts* (files), like a compiler, not ephemeral execution, like an interpreter. The IR-relevant
property is not the metaphor — it is **reliability of realization**. `realization` captures the real
distinction directly and sidesteps a metaphor that could mislead the schema. Design in terms of
determinism, not interpretation.

## `realization` is a genuine fourth orthogonal facet

`NODE-SCHEMA.md` §1a already models facets: Category ⊥ Orientation ⊥ RouteState, each `<facet>:<value>`.
`realization` qualifies as a fourth **canonical, orthogonal** facet — invariant 5 ("never infer one axis
from another") holds:

- **Not inferable from RouteState.** `route:sdk_emitted` spans *both* `realization:deterministic` (the `$0`
  cascade) *and* `realization:llm` (Prime-generated integration). Emission-origin ≠ generation-regime.
- **Not inferable from Category or Orientation.** A `category:service` node can be either regime; a
  `human`-oriented artifact can be deterministically rendered or human-authored.

| Facet | Question | Values |
|-------|----------|--------|
| Category | what domain? | service · business · pipeline · project · ai_agent |
| Orientation | who consumes? | system · human · bridge |
| RouteState | who emits / why skipped? | sdk_emitted · owned_elsewhere · declared_unimplemented · external_convention |
| **`realization`** | **how was it produced — how do I trust it?** | **deterministic · llm · human** |

## The deep coupling: `realization` determines the *verification obligation*

This is why the facet is more than a provenance tag, and why it is **coupled to the ADR** (verify/approve).
The three realization values map exactly onto three **trust regimes** — the honest restatement of the
NLPS's reliability architecture:

| `realization` | Trust regime | The obligation | ADR field |
|---------------|--------------|----------------|-----------|
| `deterministic` | **trust-by-construction** | the compiler is correct; oracle *optional* | `verify` optional |
| `llm` | **trust-by-verification** | the interpreter is stochastic; oracle **required + passing** | `verify` load-bearing |
| `human` | **trust-by-approval** | the ambiguous step; the human gate must be crossed | `approve` crossed |

> **Proposed invariant 9 — realization determines the verification obligation.** A `realization:llm` node
> is never trusted without a passing `verify` oracle; a `realization:human` node without a crossed
> `approve`; a `realization:deterministic` node is trusted by construction. *Never ship an LLM realization
> on faith.*

The clean NLPS story was "`NL→contract` human-gated + `contract→product` deterministic." Reality is that
`contract→product` has **two regimes**, and the LLM regime *breaks* the determinism guarantee. The
`realization` facet makes the story honest: `contract→product` is trusted-by-construction where
`realization:deterministic`, and interpreted-then-**verified** where `realization:llm`. The facet + the
ADR's `verify`/`approve` are one coherent design — the IR becomes the ledger of *"how do I trust this node?"*

## Granularity: a per-leaf scalar that rolls up — and the rollup IS the determinism metric

A REQUIREMENT node is typically *mostly* deterministic (CRUD/pages/views) with a few LLM integration
leaves. So `realization` is **per-leaf**, and a parent's realization is a **distribution**, not a scalar
— consistent with the schema's existing roll-up discipline (status min-rolls-up; RouteState fixes the
denominator per facet). A leaf is one regime; "mixed" is a *rollup* property, never a leaf value (this
avoids a muddy `hybrid` value and mirrors how §1a keeps facets clean).

The payoff is large: **rolled up to the summary altitude (SV-4 core/derived class), the `realization`
distribution IS the observable determinism-%** — the "~89% deterministic" claim the whole SDK strategy is
organized around, turned from an ad-hoc narrated figure into a first-class, per-app number *derived from
the IR*. "This app: 28 entities deterministic, 3 llm-integration, 0 human-authored — 90% `$0`." That is
the determinism story made glance-approvable, per the descriptive-layer invariant (never `--json`-only).

## Provenance depth: the interpreter needs a richer sidecar — and it already exists (Mottainai)

A deterministic realization is a *pure function of the contract* → reproducible; `lives: code` + digest
suffices. An LLM realization depends on `(contract + model + prompt-version + seed + context)` → to be
auditable/reproducible it needs richer provenance: which model, which prompt-version, what cost. **That
data already exists** — the Kaizen registry enrichment (`micro_prime/engine.py`, `exemplars/registry.py`)
stamps generation metadata (strategy, model, timing, AST validity) per element; `backend_codegen/ai_layer.py`
carries the source-bound `binding`/`source_id`; `costs/` tracks per-request cost. Expressing the
interpreter in the IR is therefore a **lift, not a build**: attach the existing generation-metadata to a
`realization:llm` node's `lives` evidence (`generated_by: {model, prompt_version, cost, seed}`), so the
IR references the provenance it currently discards. `realization:deterministic` nodes carry none of this
(they don't need it) — a natural asymmetry, not accretion.

## Discipline: keep the values coarse (IR-neutrality)

The failure mode is encoding back-end *mechanics* into the IR (`realization:prime-micro-splice`,
`realization:repair-step-14`) — which re-couples the IR to today's construction internals and violates the
anti-premature-generalization rule (CL-11/36/37). The values stay **coarse, neutral categories**
(`deterministic|llm|human`); the facet mechanism (`<facet>:<value>`) already allows a domain to extend the
value set without touching the core. Finer realization detail lives in the `lives.generated_by` sidecar,
not in the facet.

## Modularity: is `realization` general or SDK-specific?

The key cross-repo question (don't pollute the shared IR with SDK back-end specifics). Verdict: **general
enough to be a canonical facet.** "How was this realized / how do I trust it" is universal — a legal
provision is `human`-realized, a generated brief could be `llm`, a rendered form `deterministic`. The
*facet* is shared (like Orientation); the *value set* is extensible per domain. So it belongs in the
shared schema, not an SDK-only extension — but its most load-bearing use (the determinism-% cost story)
is SDK-specific, which is fine: a shared facet with a domain-specific killer app.

## Does it pass the schema's own bar? (simplification, not accretion)

`NODE-SCHEMA.md` demands a new axis *remove* more code-paths than it adds (the OTel taxonomy dissolved 5
smells over 4 CRP rounds). `realization` plausibly qualifies: it (a) replaces the scattered, narrated
determinism-% computation with a derived rollup, (b) makes the verify-obligation rule *explicit and
enforceable* (invariant 9) instead of implicit-and-enforced-nowhere, and (c) gives cost/reliability
reasoning a single home (today spread across `costs/`, Kaizen, the complexity classifier). **Honest
caveat:** the evidence is weaker than the OTel case — this is a *predicted* simplification, to be proven
by a CRP round before adoption, not asserted.

## Open research questions

- **OQ-1 — Planned vs realized.** Should the router's *planned* realization be a distinct field from the
  *realized* one? Their **delta** (planned-deterministic but realized-llm) is a determinism-regression /
  cost-leak signal — the Kaizen `assembly_delta` idea applied to realization. (Likely a v2 refinement; v1
  = one realized facet, router stays external.)
- **OQ-2 — Enforcing invariant 9 without blocking spec-stage nodes.** `realization:llm ⟹ verify required`
  must fire only once `lives` is non-empty (mirror the `ships_when ⟺ lives-empty` invariant), else every
  unbuilt spec node fails. Define the activation edge.
- **OQ-3 — Provenance: lift or reference?** Minimal `generated_by` on `lives` vs a pointer to the Kaizen
  sidecar. (Reference first, to avoid duplicating the registry; lift the few fields the summary needs.)
- **OQ-4 — Rollup semantics.** Is the summary the *count distribution* (28/3/0) or a single %? Both? How
  does a `realization:llm` leaf with a *failing* `verify` render (a determinism claim with a broken oracle)?
- **OQ-5 — Cross-repo value set.** Do non-SDK adopters (legal/benchmark) need different `realization`
  values, and does the shared schema enumerate a canonical set + allow extension (like RouteState)?
- **OQ-6 — Interaction with the derivation edge (REQ-16).** A node's `realization` and its
  `derived_from` chain together answer "what produced this, from what?" — is realization a property of the
  node or of the *derivation edge* (the transform), i.e. does the edge carry the regime? (Edge-carried
  realization may be the more correct model: the *transform* is deterministic or stochastic, not the node.)

## Sequencing against the committed work

1. **ADR first** (verify/approve/was) — establishes the fields invariant 9 depends on.
2. **REQ-16** (derivation edge + conformance) — establishes the transform edge OQ-6 may attach realization to.
3. **Then `realization`** — a `/reflective-requirements` REQ + a CRP round to test the simplification claim,
   landing the facet, invariant 9, the `lives.generated_by` reference, and the summary-altitude rollup.

The facet is not urgent, but it is the piece that makes the IR express the *whole* system honestly: two
back-ends, three trust regimes, one ledger of how each node is realized and why it can be believed.
