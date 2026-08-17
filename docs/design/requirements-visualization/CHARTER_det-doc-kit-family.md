# Charter — the det-doc-kit family

**Date:** 2026-08-17 · **Type:** governing charter · **Status:** proposed
**Governs:** the family of deterministic document-format kits formalizing the NLPS document layer.
**Grounds:** `ARCHITECTURE_the-det-doc-kit-family.md` · `dev-os/det-req-kit/` (the origin kit) · the NLPS thesis.

## 1. What this family is

The NLPS document layer is a **`$0`-derivation cascade** from one human-gated requirement down to code/tests/docs,
bracketed by two irreducibly-human bookends. The **det-doc-kit family** formalizes every document *between* the
bookends — each such document is a `$0` projection of the requirement, and each gets a `det-<doctype>-kit` that
versions its format. `det-req-kit` is the origin and the proof-of-concept; `det-plan`, `det-crp`, and
`det-handoff/howto/ledger` are its members.

## 2. The core invariant (the reason the family stays thin)

> **Every kit owns a FORMAT, never a generator.**

A kit versions a grammar (`SCHEMA.md` + `*.schema.json`) + a thin validator (`extract.py`-style) + templates +
worked examples. The **generator** (the `$0` projector that produces the doc) is **cited, not restated**
(Mottainai). This one rule prevents kit-sprawl into engines and keeps each kit a *documentation of an existing
deterministic system*, which is the surest sign a kit was latent all along.

## 3. Membership criteria — what qualifies a doc-type for a kit

A doc-type joins the family **iff all** hold:
1. **Projection** — its content is a `$0` derivation of an upstream structured doc (derivable, not authored).
2. **Between the bookends** — it is neither a front-bookend source (INTENT/ADR/RESEARCH) nor a back-bookend
   reflection (RETROSPECTIVE/§0).
3. **Recurring grammar** — ≥2 real instances share a structure (measured, not asserted).
4. **Never-inferred** — the derivation is deterministic; nothing is LLM-invented (the `det-req-kit §9` rule).

## 4. Exclusion criteria — what stays prose (the bookends)

Formalizing a bookend doc is **false precision** — do not do it.
- **FRONT (author the contract):** VALUE_PROP/INTENT · RESEARCH/ANALYSIS · ADR · the FR `does`/`Verify` clauses ·
  the `Approve?` gate. *(Ambiguity legitimately lives here — the DATA MODEL bookend.)*
- **BACK (reflect on actuals):** HANSEI/RETROSPECTIVE · the §0/§0.1/§0.2 feedback markers · the *selection*
  judgment inside HARVEST/YOKOTEN. *(The essential complexity Brooks says no tool removes.)*

## 5. The shared kit structure (every member mirrors det-req-kit)

- `README.md` — abstraction + backends · `SCHEMA.md` — the **versioned field spec (the format)** ·
  `<doc>.schema.json` — the machine contract · `extract.py` — thin markdown→JSON extract + schema-validate +
  the **liveness gate** (CI-droppable, `exit 1` on schema / dangling ref) · `new.py` — skeleton generator (no
  content-from-intent) · `templates/` · `examples/` · `tests/` (good + `.bad` fixtures).

## 6. Cross-cutting invariants every kit inherits

1. **`$0` derivation** — content projects from upstream; nothing LLM-inferred.
2. **Liveness, stratified by altitude** — a declared companion/reference must be **LIVE**, not `PHANTOM`/`LEGACY`/
   `ABSENT`; each kit's census counts **LIVE only**. This is verify-liveness (REQ-22) lifted to the kit's own
   altitude (`FR-gate → REQ-verify → PAIR-companion → corpus-coverage`).
3. **Anti-inflation maturity ladder** — a *projected* artifact starts at the lowest rung (`0.1`) and climbs only by
   earning hardening evidence (`§0.1`/`§0.2`/CRP). Never claim maturity unearned.
4. **Solo-vs-gap honesty** — distinguish "legitimately has no companion (by design)" from "companion owed but
   absent." The projector fires **only on the gap** — *never invent ceremony* (reflective-pairs G-5).
5. **DIDL naming** — every kit-governed artifact carries a semantic name + readable handle + canonical ref; no
   integer-only names.

## 7. The roster

| Kit | Formalizes | Status | Origin |
|-----|------------|--------|--------|
| **det-req-kit** | the REQUIREMENT (FRs) | **SHIPPED** | 🔴 thin source (the origin) |
| **det-plan-kit** | the PLAN | **next** — grammar spec authored | 🟡 `$0` projection of REQ (schema already in det-req-kit §9) |
| **det-crp-kit** | the CONVERGENT REVIEW (focus + Appendix-A/B/C review-log) | assessed → **thin** | 🟡 `$0` (compiler `new-cnvrg-rvw-prmpt` already runs) |
| **det-handoff-kit** | the HANDOFF | candidate | 🟡 `$0` projection of REQ+ledger |
| **det-howto-kit** · **det-ledger-kit** | HOWTO/generated docs · the ledger | candidate (terminal, lower value) | 🟢 output/state projection |

## 8. Governance

- **Home:** kits live in `dev-os/` alongside `det-req-kit/` (cross-repo — kit-owner's go to add a member). The SDK
  side registers the **projectors** (like `backend_codegen`) under the deterministic-providers entry-point group.
- **Versioning:** `det-<doc>/0.1 → 0.2` is lineage (a version bump), never a label.
- **Design home:** this charter + the member grammars are authored in `startd8-sdk/docs/design/requirements-visualization/`
  (the NLPS design corpus) and adopted into the dev-os kit dirs when landed.

## 9. Sequencing

1. **det-plan-kit** (grammar `SCHEMA_det-plan-0.1.md` authored alongside this charter; projector next).
2. **det-crp-kit** — thin: version the focus + review-log schemas, add `crp_lint.py`.
3. **det-handoff / det-howto / det-ledger** — complete the family as demand warrants.

**The charter in one line:** *formalize every document between the two human bookends, one `det-<doc>-kit` per
projectable doc-type, each owning a format and citing its generator — so the NLPS document layer becomes an
inspectable, `$0`, liveness-gated cascade, and the only prose left is the two bookends that carry the judgment.*
