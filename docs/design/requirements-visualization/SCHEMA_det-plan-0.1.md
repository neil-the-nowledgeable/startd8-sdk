# det-plan v0.1 — the field specification

**Date:** 2026-08-17 · **Type:** format grammar (a det-doc-kit member) · **Status:** proposed
**Governed by:** `CHARTER_det-doc-kit-family.md` · **Mirrors:** `dev-os/det-req-kit/SCHEMA.md`
**Supersedes-by-formalizing:** `det-req-kit/SCHEMA.md §9` (the `plan{}` schema that already exists inline).

> A **det-plan is a `$0` projection of a det-req** — it sequences the requirement's FRs into an ordered,
> batched, gated build schedule. It is **derived, never authored**: every input it needs (FRs, `Touches`,
> the authored acyclic dependencies, `Verify`) already lives in the det-req. The generator (the projector) is
> **cited, not defined here** (charter §2) — this doc owns the FORMAT only.

## 0. Provenance — the schema already exists; this names it

`det-req-kit/SCHEMA.md §9` already defines `plan = {iterations[], dependencies[], budgetRef}` with the rule
*"deps `F-x after F-y` are authored & acyclic, **never inferred**."* det-plan/0.1 lifts that inline block into a
first-class, versioned grammar and adds the three foundations the reflective-pairs index proved
(companion-kind + maturity ladder + plan-liveness). Nothing here is new invention; it is documentation of a
latent format.

## 1. Document header **[core]**

| Field | Type | Req'd | Meaning | Derivation |
|-------|------|-------|---------|------------|
| `version` | semver | yes | doc lineage (0.1→0.2…), not a label | authored on the plan |
| `formatVersion` | const `det-plan/0.1` | yes | which kit schema this obeys | this doc |
| `pairsWith` | path | yes | the det-req this plans — **MUST resolve LIVE** (§6) | the source req |
| `companionKind` | enum `PLAN` | yes | the projector emits **only** `PLAN` (never for a solo-by-design REQ) | §8 honesty rule |
| `maturity` | enum `0.1 · 0.2 · 0.3[.n] · 0.4-post-CRP · 0.5 · v1.x` | yes | **a projected plan starts at `0.1`** (§7) | anti-inflation |
| **DIDL** `name`/`handle`/`ref` | strings | yes | semantic name + `{kind}/{slug}-{8hex}` + `cc:intent:…` | `naming.name_forms` |

## 2. Iterations **[core] — the heart** (mirrors det-req's FRs)

`iterations[] = { id, name, frs[], targetFiles[], dependsOn[], gate, costClass, status }`, batched
`foundation → logic → integration` (§9 keeps this to a small number).

| Iteration field | Derivation from the det-req |
|-----------------|------------------------------|
| `id` | `F-n` (sequence) |
| `name` | DIDL semantic (actor·action·object·outcome) |
| `frs[]` | **which req FRs this iteration realizes** — the grouping (batch FRs that share `Touches`/dependency) |
| `targetFiles[]` | **derived from the FRs' `Touches`** (the files each FR edits/creates) |
| `dependsOn[]` | `F-x after F-y` — **derived from the FR dependency topology** (`Serves`/`Touches`/`Pairs-with`); **acyclic, never inferred beyond the req's authored deps** |
| `gate` | **the exit criterion — derived from the FRs' `Verify:` clauses** (the requirement→test seed, per-iteration) |
| `costClass` | `deterministic-$0 · llm-integration · human` — **derived from the realization regime** (REQ-18/19); rolls up to a plan-level cost estimate |
| `status` | `planned · done` |

## 3. Dependencies **[core]** — the DAG

The iteration dependency graph. **MUST be acyclic** (reuse `queue.py` cycle detection — the same guard the
corpus DAG self-study used). Derived from the FR topology; the det-req's authored dependencies are the sole
source (the projector **does not invent** an edge — §8).

## 4. Reuse (Mottainai) **[core]**

The existing modules the plan touches — **derived from the FRs' `Touches`/`Lives`** (which refs are existing vs
to-be-created). Includes the **phantom audit**: each `Lives`/`Touches` ref is resolved on disk; a claimed-existing
ref that is absent is a flag (the honest-grounding check, at the plan altitude).

## 5. Verify (whole change) **[core]**

The plan-level exit criteria — the **rollup of the FRs' `Verify:` clauses** (requirement→test traceability,
aggregated). No iteration enters the plan without its FRs' `Verify` carried forward — the det-req rule *"no FR
enters the plan without a verify"* is inherited as *"no iteration ships without its gate."*

## 6. Plan-liveness **[core]** — the pair-altitude present-but-dead cell

`pairsWith` MUST resolve **LIVE**. The resolver classifies every plan↔req link:

| Status | Meaning | Instance (on disk today) |
|--------|---------|--------------------------|
| **LIVE** | target is a real det-req PLAN companion | (the goal) |
| **PHANTOM** | declared, but the file is **absent** | `visual-editor/REQ-05-Traceroute` → `PLAN-05` (does not exist) |
| **LEGACY** | file exists, but no `§0`/det-req markers | `antigravity-loop/PLAN-23` (legacy prose) |
| **ABSENT** | no declaration | a spec-only REQ with no `Pairs with:` |

A "paired" census that counts `PHANTOM`/`LEGACY` is a survivorship lie. **Count LIVE only.** This is
`verify-liveness-not-presence` (REQ-22) lifted from the FR↔check invariant to the REQ↔PLAN invariant — the
pair-altitude cell of the liveness column.

## 7. Maturity — the anti-inflation ladder

A **projected** plan is `maturity: 0.1` (mechanically derived, `§0`-only, un-hardened). It climbs **only** by
earning evidence: `§0.1` (lessons-hardening) → `§0.2` (principle-hardening) → CRP (survived a convergent review).
A plan MUST NOT declare post-CRP maturity it has not earned. *(Rungs mirror the reflective-pairs ladder
`0.1 → v1.2`.)*

## 8. Honesty rules **[core]**

- **Solo-vs-gap:** the projector emits a plan **only** for a REQ that *owes* one (the `*(plan deferred — plan
  follows)*` marker); it emits **nothing** for a `NONE`/solo-by-design REQ (charter §6.4; reflective-pairs G-5
  *"do not invent PLANs for ceremony"*).
- **Never-inferred:** the iteration grouping and the dependency order derive from the req's **authored** structure;
  the projector does not invent a dependency the req did not declare (`det-req-kit §9`).
- **Anti-inflation:** §7 — a projected plan starts at `0.1`.

## 9. The projector — CITE, don't define (Mottainai)

The `$0` REQ→PLAN projector is **not specified here** (charter §2 — the kit owns the format, not the generator).
It reuses: `queue.py` (acyclic ordering + cycle detection) · the navigator graph projection (the dependency
topology) · the realization regime (REQ-18/19 → `costClass`). It is registered SDK-side under the
deterministic-providers group (like `backend_codegen`). Because all its inputs live in the det-req, the projection
is `$0` and satisfies "never inferred" **by construction**.

## 10. Conformance (the `extract.py` gate — what a validator checks)

A det-plan/0.1 doc is conformant iff: `formatVersion == det-plan/0.1`; `pairsWith` resolves **LIVE** (§6);
every `iteration.frs[]` references an FR that exists in the paired req; `dependsOn[]` is **acyclic** and every edge
traces to an authored req dependency (no invented edges); every iteration carries a `gate` (§5); `maturity` is not
inflated beyond earned evidence (§7); and `companionKind == PLAN` (a solo REQ has no plan doc at all). A
`.bad` fixture (cyclic deps · phantom `pairsWith` · an FR-less iteration · an invented dependency) must fail the
gate `exit 1`.

*v0.1 — formalizes `det-req-kit §9`'s inline plan schema into a versioned det-doc-kit member; adds the
companion-kind / maturity-ladder / plan-liveness foundations proved by the reflective-pairs index. The projector
is the next artifact (cited, not defined here).*
