# Reference: Weaver (and the "Loom") as the governance + fidelity mechanism for business instrumentation

**Date:** 2026-08-19 · **Type:** reference / tool-grounding · **Status:** connects an existing tool
(OTel **Weaver**, already in the ContextCore stack) to the C1 (registry) + C2 (fidelity) convergences
from `SYNTHESIS_divergent-analysis-findings.md`. Answers: *what carries the "governed registry" and the
"map-fidelity oracle" the synthesis said we lack — and what is the "Loom"?*

---

## 0. TL;DR

The two strongest synthesis findings — **C1** (the `route→flow→criticality` map should be a *governed
registry*, not a linted table) and **C2** (its *fidelity* to the running system is unguarded) — do **not**
need a bespoke mechanism. **OTel Weaver already provides both**, and it is **already in this ecosystem**:
ContextCore runs a Weaver semantic-convention registry today, and the manifest **reserves `business.yaml`
as a planned group**. Weaver's three verbs map exactly onto the gap:

| Synthesis finding | Weaver mechanism | What it does |
|---|---|---|
| **C1** — governed *vocabulary* (allowed-values, versioned) | **`weaver registry` (the registry itself)** | the `business.*` namespace as a declared, versioned semconv group — the single source of truth |
| **C1** — governed *enforcement* (the PDP, not a lint) | **`weaver registry check` + Rego policy** | policy-as-code over the registry — the externalized decision point the zero-trust analogy (OPA PDP/PEP) said we were one rung short of |
| **C2** — *fidelity* to the running system | **`weaver registry live-check`** | validates **live telemetry** against the declared registry — the discovered-vs-declared reconciliation that closes the "confidently-wrong RCA" hole |

**"Loom" is not a tool** — zero hits across startd8-sdk, ContextCore, and dev-os. It reads best as the
*complementary framing* to Weaver (§3): if Weaver threads the **weft** (the declared `business.*` meaning
woven across spans), the **Loom** is the **warp** — the live trace structure (root-span entry routes) held
under tension, against which the woven pattern is checked. That warp is exactly what the C2 fidelity gate
*reads* to reconcile. Whether "Loom" becomes a named component or stays a metaphor is a call for you (§4).

## 1. What Weaver is (grounded, not from memory)

**OTel Weaver** is the OpenTelemetry project's semantic-convention toolchain: you declare attributes/metrics/
spans/events in a **registry** (YAML groups), and Weaver (a) generates code/docs/enums from it, (b) enforces
policy over it with **Rego** (`weaver registry check`), and (c) **`weaver registry live-check`** — consumes a
stream of *real* telemetry (OTLP/JSON) and reports attributes/values that are missing from, mistyped against,
or absent-in the declared registry. That third verb is the one that matters here: it is a **fidelity oracle**
by construction — declared registry vs. observed reality.

**It is already in your stack (grounded):**
- `ContextCore/semconv/registry_manifest.yaml` — a live Weaver registry, *"OTel Weaver-compatible registry
  formalizing ~185 attributes across 17+ namespaces,"* with `registry/task.yaml`, `project.yaml`, `sprint.yaml`,
  `agent.yaml`, `lesson.yaml` **implemented**, and — decisively — **`# - registry/business.yaml`** listed under
  *"Phase 2 (planned)."* The `business.*` namespace the whole corpus calls "absent" is in fact **reserved**.
- `ContextCore/src/contextcore/.../weaver.py` — *"Cross-repo schema alignment."*
- `ContextCore/tests/test_workitem_semconv_contract.py` — proves the registry-as-CI-contract pattern already runs.
- `startd8-sdk/scripts/gen_semconv_domains.py` — the SDK already generates semconv domains (the Weaver-adjacent
  codegen seam on this side).

So the corpus's "own the `business.*` semconv namespace" play (intro doc 05) and its "governed registry" gap
(C1) resolve to the **same, already-instantiated mechanism**: add the reserved `business.yaml` group.

## 2. How Weaver closes C1 and C2

### C1 — the map becomes a Weaver registry group + a Rego policy (the PDP)
Author `route→flow→criticality` as the `business.yaml` registry group (allowed-value enums for `business.flow`
and `business.flow.criticality`; the non-colliding names from the roadmap's §4.2). `weaver registry check` runs
Rego policy over it in CI — that is the **externalized decision point** the zero-trust analogy (Angle C) said we
were one maturity rung short of: not a lint over a copied table, but policy-as-code the consumers reference.
The coverage-% / unmapped-bucket / lifecycle that FinOps + product-analytics converged on (Angle C) are the
registry's own health surface. **Over-abstraction guard:** one registry group + policy now; a full queryable
PDP service only at ≥2 declared tables or real drift.

### C2 — `weaver registry live-check` IS the map-fidelity gate (FR-9)
The synthesis's highest-severity hole: FR-1 guards *consistency*, FR-6 guards *reach*, nothing guards
*fidelity*, so a stale/wrong map runs the RCA de-blending backwards into **confidently-wrong** results while
both guards stay green. The metabolized **FR-9** closes it with a discovered-vs-declared reconciliation, and its
**operational engine is `weaver registry live-check`**: sample real assembled traces → the live `business.*`
values (and the root-span entry route that should have produced them) are checked against the declared
`business.yaml` registry + the `route→flow` map → **alarm on divergence + unmapped-route drift.** It fails loud
when `/cart/checkout` is declared `browse`; it passes when the weave matches the warp.

**The honest tension, held:** live-check reads *reality*, which brushes the corpus's load-bearing "declared,
not discovered" discipline. It stays intact because live-check is an **adversarial drift-guard *on* the
declaration** — it samples the world to ask *"does your declaration still match?"* and never authors or
back-fills a value (a human fixes the declaration; the gate never auto-reconciles). This is the identical
framing REQ-22 used to fix the repo's prior instance of this exact class (presence≠liveness / "verification
that cannot silently die").

## 3. The "Loom" — an honest reading

**There is no `Loom` in any repo** (startd8-sdk, ContextCore, dev-os — grepped, zero hits). So this section is
*framing*, not documentation of a thing. The loom/weaver pairing is, however, unusually apt for the fidelity
mechanism:

- A loom holds the **warp** — the fixed structural threads under tension. Here the warp is the **live trace
  structure**: the assembled span tree and its root-span entry route — *what actually happened*, independent of
  any declaration.
- The **weaver** passes the **weft** across the warp — here, the declared `business.flow` woven onto the spans.
- **Fidelity = does the woven pattern match the warp it was woven on?** The C2 gate literally reads the warp
  (root-span route, via trace-derivation — the C5 carrier) and checks it against the weft's declared pattern
  (the registry map). Weaver supplies the weft + the checker; the **Loom is the live-telemetry substrate the
  checker reads** — today that's just "the trace store `live-check` samples," un-named.

So "Loom" could be promoted to a **named component**: the live-reconciliation substrate that (a) assembles
traces, (b) derives the warp (root-route→flow) for the analysis-path carrier (C5), and (c) feeds
`live-check`. That would give the fidelity loop a home distinct from Weaver (the schema side). Or it stays a
metaphor and `live-check` + the trace store suffice. **This is a naming/architecture decision for you** — see §4.

## 4. Open questions (for you)

1. **Promote "Loom" to a component, or keep it as framing?** If promoted, it's the live-trace substrate that
   owns trace-derivation (C5) + feeds `live-check` (C2) — a clean counterpart to Weaver (declared side). If
   not, `weaver registry live-check` over the existing trace store is enough and we don't coin a term.
2. **Land the reserved `business.yaml` registry group now?** It's the concrete first step for C1 and it's
   already reserved in the ContextCore manifest — low-cost, high-signal, and it anchors FR-9's `live-check`.
3. **Who owns it — ContextCore or the SDK?** The registry + `weaver.py` alignment live in ContextCore; the
   carrier + generation seam (`gen_semconv_domains.py`) is SDK-side. FR-1/FR-9's `Touches` already span both.

## 5. Maturity (honest)

- **Weaver registry in ContextCore** — **shipped** for `task/project/sprint/agent/lesson`; `test_workitem_
  semconv_contract.py` runs the check in CI.
- **`business.yaml` group** — **reserved/planned** (commented in the manifest), not authored.
- **`weaver registry check` + Rego policy for `business.*`** — **roadmap** (no `.rego` for business yet).
- **`weaver registry live-check` wired as the FR-9 fidelity gate** — **roadmap** (the mechanism is upstream-real
  and CI-proven for other groups; wiring it to `business.flow` + the route→flow map is the new work).
- **"Loom" as a named component** — **does not exist**; a framing + an open decision (§4).

**One-line:** *the governed registry and the map-fidelity oracle the synthesis said we lacked are already a
tool we run — OTel Weaver (`registry` + `check`/Rego + `live-check`), with `business.yaml` reserved and
waiting — and the "Loom," if we want it, is the name for the live warp that fidelity is checked against.*
