# det-crp v0.1 — the field specification

**Date:** 2026-08-17 · **Type:** format grammar (a det-doc-kit member) · **Status:** proposed
**Governed by:** `CHARTER_det-doc-kit-family.md` · **Mirrors (essentials only):** `SCHEMA_det-plan-0.1.md`
**Formalizes:** the latent CRP format already on disk — `crp-focus-*.md` (the focus) + the Appendix-A/B/C review-log
embedded in every CRP'd REQ/PLAN. **Generator already runs:** `new-cnvrg-rvw-prmpt` (the prompt compiler).

> A **det-crp is the CONVERGENT REVIEW of a doc** — a small human-authored **focus** plus an append-only
> **review-log** (Appendix A/B/C) that accretes across rounds. Unlike det-plan it is **NOT a `$0` projection**:
> the review-log is *authored/accreted* by reviewers, and the review *prompt* is already `$0`-**compiled** by
> `new-cnvrg-rvw-prmpt`. So this kit is **thin — format + lint**, and its generator is **cited, not defined**
> (charter §2). *(This is the mirror-inertia guard in action: det-crp mirrors det-plan-0.1's format-essentials
> only; it has **no** projector, no `iterations`/`dependsOn`/`costClass` — those are det-plan-specific.)*

## 0. Provenance — the format already exists; this names it

Two artifacts recur, measured across ≥2 real instances (charter §3 membership rule):
- **The focus** — `crp-focus-sdk-node-home.md`, `crp-focus-seat-requirement-authoring.md` (least-reviewed target ·
  do-not-re-litigate · where-input-needed).
- **The review-log** — the `Appendix A: Applied` / `Appendix B: Rejected` / `Appendix C: Incoming` block +
  "Reviewer Instructions" in `PLAN-01-sdk-node-home.md`, `PLAN-nl-programming-pipeline-provenance.md`, and every
  other CRP'd doc.

Nothing here is new invention; it documents a latent format and versions it, exactly as det-plan/0.1 did for
`det-req-kit §9`.

## 1. Document header **[core]** (mirrors det-plan-0.1 §1)

| Field | Type | Req'd | Meaning | Derivation |
|-------|------|-------|---------|------------|
| `version` | semver | yes | doc lineage (0.1→0.2…), not a label | authored |
| `formatVersion` | const `det-crp/0.1` | yes | which kit schema this obeys | this doc |
| `pairsWith` | path | yes | the reviewed **REQ/PLAN** — **MUST resolve LIVE** (§6) | the reviewed doc |
| `companionKind` | enum `CRP` | yes | a review is emitted **only** for a doc that *owes* one (§8 solo-vs-gap) | §8 |
| `maturity` | enum `0.1 · 0.2 · 0.3[.n] · 0.4-post-CRP · 0.5 · v1.x` | yes | a fresh focus is `0.1`; it climbs **only** by surviving real rounds (§7 anti-inflation) | §7 |
| **DIDL** `name`/`handle`/`ref` | strings | yes | semantic name + `{kind}/{slug}-{8hex}` + `cc:intent:…` | `naming.name_forms` (`kind="crp"`) |

## 2. The focus **[core]** — the small authored half

`focus = { leastReviewedTarget, doNotReLitigate[], inputNeeded[] }` — the reviewer's scope contract.

| Focus field | Meaning |
|-------------|---------|
| `leastReviewedTarget` | the one thing this round most needs eyes on (the survivorship-bias antidote) |
| `doNotReLitigate[]` | settled decisions (from REQ §0 / PLAN discoveries) — reviewers must **not** re-open |
| `inputNeeded[]` | the open questions where input is wanted most (numbered) |

## 3. The review-log **[core]** — the append-only accreted half (Appendix A/B/C)

The cross-model memory. **Append-only**: A and B are **never deleted** (they stop later reviewers re-proposing).

| Section | Shape | Rule |
|---------|-------|------|
| **Appendix C — Incoming** | `Round{ n, reviewer, date, scope, suggestions[] }`; each `suggestion{ id, area, severity, suggestion, rationale, placement, validation }` | append a `#### Review Round R{n}` block; ids unique `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements) |
| **Appendix A — Applied** | `{ id, suggestion, source, where-merged, date }` | an accepted C-suggestion moves here with its merge location |
| **Appendix B — Rejected** | `{ id, suggestion, source, rejection-rationale, date }` | a rejected C-suggestion moves here **with a rationale** (never silently dropped) |

## 4. Triage completeness **[core]** — nothing dropped

Every suggestion in Appendix C is either **triaged** (appears in exactly one of A/B, by id) or explicitly **pending**.
A suggestion that vanishes from C without an A/B disposition is a **dropped-finding** violation — the CRP's whole
value is that no raised concern is silently lost (the cross-model memory rule).

## 5. Reviewer contract **[core]**

The "Reviewer Instructions" preamble is part of the format: scan A/B **before** suggesting (no re-proposing settled/
rejected items); append to C with unique ids; endorse prior items rather than restate; the orchestrator triages to
A/B. This is the *behavioral* contract `new-cnvrg-rvw-prmpt` bakes into the compiled prompt.

## 6. Liveness **[core]** (mirrors det-plan-0.1 §6, same altitude-lifted invariant)

`pairsWith` MUST resolve **LIVE** — a review-log pairing a `PHANTOM`/`ABSENT` reviewed doc is a survivorship lie
(you reviewed something that isn't there). Same `LIVE / PHANTOM / LEGACY / ABSENT` classes; **count LIVE only**.

## 7. Maturity — the anti-inflation ladder (mirrors det-plan-0.1 §7)

A fresh focus is `0.1`. It climbs **only** by earning it: a doc reaches `0.4-post-CRP` **only after a real round
triaged to A/B** — never by declaring it. A review-log MUST NOT claim `post-CRP` maturity with an empty Appendix A/B.

## 8. Honesty rules **[core]**

- **Solo-vs-gap:** a CRP is emitted **only** for a doc that *owes* review (a `Least-reviewed target` exists); a doc
  with no review owed gets **no** focus/log — do not manufacture a review round for ceremony (charter §6.4).
- **Never-inferred (for the compiled prompt):** the `new-cnvrg-rvw-prmpt` compiler assembles the prompt `$0` from the
  focus + the reviewed doc's authored content — it invents no review content; the *findings* are authored by reviewers.
- **Anti-inflation:** §7 — a fresh focus is `0.1`; maturity tracks rounds actually survived.
- **Append-only memory:** §3 — A/B are never deleted.

## 9. The generator — CITE, don't define (Mottainai; charter §2)

det-crp has **no `$0` projector** (unlike det-plan) — the review-log is human/model-*accreted*, not projected, and the
one `$0` step (the review **prompt**) is **already compiled** by the **`new-cnvrg-rvw-prmpt`** skill (focus + reviewed
doc → prompt; persists Appendix-C rounds, triages to A/B). This kit therefore ships **format + lint only**: a
`crp_lint.py` conformance gate (charter §9.2). It does **not** register an SDK deterministic-provider.

## 10. Conformance (the `crp_lint.py` gate — what a validator checks)

A det-crp/0.1 artifact is conformant iff: the focus carries a non-empty `leastReviewedTarget`; every Appendix-A/B row
references a real C-suggestion id (no orphan dispositions); no id is **double-triaged** (in both A and B); A and B are
present (append-only, may be empty on round 1); and — when the artifact declares them — `formatVersion == det-crp/0.1`
/ `companionKind == CRP` / `maturity` not inflated / `pairsWith` LIVE. Findings emit as **SARIF 2.1.0** via the ONE
`coverage_map/findings_sarif` (imported, not vendored — charter §5/§6).

> **BUILT + dogfood fold-back (`src/startd8/crp_lint/` + `scripts/crp_lint.py`, 12 tests):** two rules the first draft
> listed do NOT survive contact with real accreted review-logs, and the build corrected them:
> - **id-uniqueness is authoring-time, not lint-time.** A naive "an id appears twice in Appendix C → duplicate" check
>   is a FALSE POSITIVE — a real review-log legitimately *references* an id many times (the round's suggestion table +
>   a coverage matrix + an endorsements list). A text lint can't tell a second *definition* (a genuine collision) from
>   a *reference*, so uniqueness is enforced by the compiler at authoring time; the lint does **not** check it.
> - **the header checks are conditional-on-presence.** A bare accreted review-log (an Appendix-A/B/C block inside a
>   REQ/PLAN) usually carries **no** det-crp header — so `formatVersion`/`companionKind`/`pairsWith`/`maturity` are
>   checked only when the artifact declares them, not required. The load-bearing checks are the review-log's *integrity*
>   (orphan disposition · double-triage · A/B scaffold) + the focus target. Dogfooded clean over the 26-doc corpus.

*v0.1 — formalizes the latent CRP format (focus + Appendix-A/B/C review-log) into a versioned det-doc-kit member,
mirroring det-plan-0.1's essentials (header/DIDL · liveness · maturity ladder · honesty · §10 conformance) and adapting
the rest (focus + review-log + triage-completeness) as justified CRP-specific choices. **Thin by design: format + lint,
generator cited (`new-cnvrg-rvw-prmpt`), no projector** — the mirror-inertia guard, applied.*
