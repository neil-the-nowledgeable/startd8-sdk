# Architecture: the det-doc-kit family — the NLPS document layer as a $0-derivation cascade

**Date:** 2026-08-17 · **Type:** architecture / strategic synthesis (3 parallel agents, consolidated) · **Status:** grounded
**Frames:** the Natural-Language Programming System (`THE_NATURAL_LANGUAGE_PROGRAMMING_SYSTEM.md`) · det-req-kit (the one shipped kit)
**Origin:** started as "build a det-plan-kit"; the census revealed det-plan is *one member of a family*.

## 0. The frame

The NLPS is a compiler whose source is prose. Deterministic codegen already proved the **downstream** edge:
`CONTRACT → {code, tests, docs}` is `$0` (backend_codegen, test_emitter). The three-agent census shows the
**same move applies UP the stack**: `req → {plan, crp, handoff}` is *also* `$0`, because each is a mechanical
projection of an already-structured requirement (the FR grammar `Name/Touches/Verify/Serves/Lives/Approve?`
is the same load-bearing shape det-req-kit already parses). **The entire document layer between the two human
bookends collapses to `$0`-derivation** — which is the honest, defensible form of the NLPS grand claim.

## 1. The logical conclusion — the `det-doc-kit` family

```
INTENT ─🔴─► det-req ─$0─► {det-plan · det-crp · det-handoff} ─$0─► CONTRACT ─$0─► {code · tests · docs} ─🔴─► RETROSPECTIVE
        gate                (the derivable doc siblings)             (the IR)       (the outputs)              gate
```
Only the two 🔴 edges need a human (the NL→contract gate = the DATA MODEL bookend; the actuals→lessons gate =
the RETROSPECTIVE bookend). Everything between is accidental machinery — and each accidental doc-type is a
`det-*-kit` waiting to be written.

| Kit | Formalizes | Status | Source vs projection |
|-----|------------|--------|----------------------|
| **det-req-kit** ✅ | the REQUIREMENT (FRs) | **SHIPPED** | 🔴 thin SOURCE (the origin kit) |
| **det-plan-kit** | the PLAN | **next** (§2) | 🟡 `$0` projection of REQ |
| **det-crp-kit** | the CONVERGENT REVIEW (focus + review-log) | **assessed → yes, thin** (§3) | 🟡 `$0` projection of REQ+PLAN |
| **det-handoff-kit** | the HANDOFF | candidate (strong grammar, no kit) | 🟡 `$0` projection of REQ+ledger |
| **det-howto-kit** · **det-ledger-kit** | HOWTO / generated docs · the ledger | candidate (lower value, terminal) | 🟢 output/state projection |

**The unifying invariant (inherited from det-req-kit): every kit owns a FORMAT, never a generator** (Mottainai
— cite the consumer, don't restate it). This is what keeps the family thin.

## 2. det-plan-kit — grounded, and *smaller than expected*

**The plan schema ALREADY EXISTS** — det-req-kit `SCHEMA.md §9` defines `plan = {iterations[], dependencies[],
budgetRef}` (≤3 iterations `foundation→logic→integration`; deps `"F-x after F-y"` **authored & acyclic, never
inferred**; a `pairsWith` path). So det-plan-kit is **mostly a projector, not a new grammar**: it deterministically
projects §9's `plan{}` from a det-req's already-authored FRs + `Touches:` (→ `targetFiles[]`) + acyclic deps —
`$0`, and it satisfies §9's "never inferred" invariant *by construction* (the inputs are all in the req).

**The demand is grounded and it's ours.** Live re-ground (the census HTML is a frozen 08-13 snapshot — the render
script only re-renders the static SSOT, it does not re-scan): `startd8-sdk` is still the worst-paired repo and
**got worse this session.** Our own `requirements-visualization/` dir: **31 REQs · 3 live PLANs · 26 spec-only-
deferred companionless REQs** (REQ-02,04,05,06,07,09..27 + the view-def-mode). Those 26 are the exact demand for a
`$0` REQ→PLAN projector — plans *owed* (`plan deferred — plan follows`) but never authored.

**Three reusable foundations (from the reflective-pairs index), all byte-grounded:**
- **Companion-kind taxonomy** `PLAN / HOWTO / EMBEDDED / NONE / LEGACY` + the **solo-vs-gap honesty rule** (index
  G-5: *"do not invent PLANs for ceremony"*). det-plan hard rule: the projector fires ONLY on a `PLAN-owed` REQ
  (the `plan deferred` marker), NEVER on a `NONE`/solo-by-design REQ. (This is REQ-27's mechanical-vs-manual split,
  one altitude up.)
- **Maturity ladder** `0.1 → 0.4 post-CRP → v1.2`, evidence-graded (`§0 / §0.1 / §0.2 / CRP`). **A projected plan
  starts at 0.1** and climbs only by earning hardening evidence — an anti-inflation contract (it must not claim
  post-CRP it hasn't survived).
- **The plan-liveness cell** — `LIVE / PHANTOM / LEGACY / ABSENT`. A `Pairs with:` declared but dead is a
  survivorship lie; the det-plan census counts LIVE pairs only. **This is verify-liveness (REQ-22) lifted from the
  FR↔check invariant to the REQ↔PLAN invariant** — the *pair-altitude cell of the liveness column*, with the
  **Traceroute phantom PLAN** (declared, file absent) and **antigravity LEGACY** (file exists, no §0) as live
  on-disk instances. Liveness stratifies by altitude: FR-gate → REQ-verify → **PAIR-companion** → corpus-coverage.

## 3. det-crp-kit — yes, but a thin schema-kit (the engine already runs)

CRP is **not one document — it is three artifacts**, and formalizing the wrong one is the trap:
- **A · `crp-focus-*`** (~150–400 words) — the **authored input**: least-reviewed target · settled/do-not-
  re-litigate boundaries · where-we-need-input-most. Irreducibly human (the sponsor's uncertainty map). CRP's
  front bookend.
- **B · `crp-prompt-*-R1`** (~78–82 KB) — the **generated bundle**, already **97–98% `$0`-derived** by the existing
  `new-cnvrg-rvw-prmpt.sh` (source-doc table via `wc` · mode · the 7 fixed review areas · reviewer contract · the
  801-line guide embedded verbatim). The only authored bytes are the injected focus file.
- **C · Appendix A/B/C** (the **review-log**, lives inside the reviewed doc; **21 docs already carry it**) — a hard
  grammar: A=Applied · B=Rejected+rationale · C=Incoming (append-only) · 7-column suggestion table · `R{n}-S/F{k}`
  IDs · alias-normalization.

**Verdict:** det-crp-kit fits the family, but as a **thin schema-kit documenting an existing deterministic
system** — the surest sign it was a latent kit all along. It **owns** A's schema + C's schema (currently buried
unversioned in a 41 KB agent guide); **cites** `new-cnvrg-rvw-prmpt` as the `$0` compiler; and **builds one new
thing**: a `crp_lint.py` conformance gate for Appendix A/B/C (the `extract.py` analog). CRP is the pipeline's
**review/lint stage** — not a third source input, but a dependent review-layer schema that *references* req+plan.
Essential residue: the focus file (pre-pass judgment) + the findings (the review LLM pass itself).

## 4. The essential residue (what stays prose)

After the family formalizes every projectable doc, the human-authored corpus reduces to **exactly the two
bookends the vision predicted**, now enumerated at the document level:
- **FRONT (author the contract):** VALUE_PROP/INTENT · RESEARCH/ANALYSIS · ADR · the FR `does`/`Verify` clauses ·
  the `Approve?` gate. *(A kit here would be false precision — this is where ambiguity legitimately lives.)*
- **BACK (reflect on actuals):** HANSEI/RETROSPECTIVE · the §0/§0.1/§0.2 feedback markers · the *selection* judgment
  inside HARVEST/YOKOTEN. *(The essential complexity Brooks says no tool removes.)*

## 5. Recommendation & sequencing

1. **det-plan-kit first** — it's mostly a projector for the §9 schema that *already exists*; the 26-REQ demand is
   ours; the foundations (taxonomy · ladder · plan-liveness) are extracted and grounded. Spec the det-plan/0.1
   grammar (own the format) + the `$0` REQ→PLAN projector (cite `queue.py`/graph-projection for the acyclic order).
2. **det-crp-kit second** — thin: version the focus + review-log schemas out of the agent guide; add `crp_lint.py`.
3. **det-handoff-kit / det-howto-kit / det-ledger-kit** — candidates; complete the family as demand warrants.
4. **The plan-liveness cell** extends the shipped liveness layer (REQ-22/23) UP to the pair altitude — a natural
   REQ once det-plan lands.

**The one-sentence conclusion:** *The NLPS document layer is a `$0`-derivation cascade from one human-gated
requirement down to code/tests/docs, bracketed by two irreducibly-human bookends — so the logical endpoint is a
**det-doc-kit family** (det-req ✅ → det-plan → det-crp → det-handoff/howto/ledger) that formalizes every doc
between the bookends, leaving only INTENT/ADR at the front and RETROSPECTIVE/§0 at the back.*

*(Consolidated from 3 parallel agents; none committed — this is the single-writer persist.)*
