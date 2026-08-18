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

## 5. The shared kit structure — a typed checklist, NOT a blanket mirror

> **The mirror-inertia guard** (metabolized via `/audit-then-metabolize`, 2026-08-17): *"mirror
> det-req-kit"* is **inertia** — det-req-kit is one *instance* that accreted process clutter, source-doc-
> specific tools, and a vendored SARIF copy. Mirroring the *instance* copies its flaws. A member mirrors
> det-req-kit's **format essentials only**; every other member is a **specific per-kit choice, justified,
> never a default.** The class this guards: *instance-accretion mistaken for template-structure.*

- **Format-essentials (mandatory, every kit):** `SCHEMA.md` (the versioned field spec) · `<doc>.schema.json`
  (the machine contract) · `extract.py` (thin extract + schema-validate + the liveness gate, `exit 1` on
  schema/dangling) · `templates/` · `examples/` · `tests/` (good + `.bad` fixtures) · a **thin** `README.md`.
- **Source-kit-only (an AUTHORED doc; a DERIVED doc has a projector INSTEAD):** `new.py` (skeleton generator)
  and a finding→doc-stub (`sarif_to_req_stub`-style). A **derived-doc kit** (det-plan, det-crp, …) has
  **neither** — its `$0` projector *is* its generator, and you cannot stub-seed a doc that is projected.
- **Reuse, NEVER vendor:** SARIF via the **one** `coverage_map/findings_sarif.py` (import it). *det-req-kit
  **vendored** a copy (`sarif.py`) kept in golden-parity sync — a mirror-drift risk; the family reuses the
  single renderer, it does not vendor a copy per kit.*
- **Never in the kit dir (the bookend-exclusion applies to the dir itself):** process/retrospective docs
  (`_HANSEI`/`_HARVEST`/`_SWEEP`/`YOKOTEN`/`ENHANCEMENT_BACKLOG`) live in the retrospective home, **not** the
  format kit. *det-req-kit mixes 8 of them into its dir — the family keeps the kit dir format-only.*
- **Per-kit specific choice (justify, don't default):** `BACKEND_ROUTING.md` (only if the doc has >1 backend) ·
  `reconcile/` (only if corpus reconciliation is in scope) · `sarif_scan.py` (batch, only if a corpus scan is needed).

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
6. **Findings interchange = SARIF (the second IR)** — a kit's `extract.py` liveness/conformance gate emits its
   findings as **SARIF 2.1.0** (the shared finding-bus — via the ONE `startd8-sdk/coverage_map/findings_sarif.py`,
   **imported not vendored**; note `det-req-kit/sarif.py` *vendored* a copy — §5's reuse-not-vendor rule exists
   so the family does not repeat that mirror-drift), so a doc defect annotates a PR / IDE exactly like a code
   finding. This is the family's tie to the NLPS's *other* IR: the **Node** is the wire-format of the document
   half; **SARIF** is the wire-format of the **findings** half. The interchange is bidirectional and closes the
   loop: inbound SARIF **seeds a source-doc stub** (`det-req-kit/sarif_to_req_stub.py` — the finding→REQ-stub
   generative role), which is deliberately a **scaffold, not a factory** (loud UNFINISHED banner; the CRP /
   human completes it — propose-don't-dispose). So `check/review/retrospect → SARIF → stub → forward loop` is
   the machine-readable, human-gated PDCA edge. *(A `Lesson` node (REQ-20) and a SARIF result are findings-half
   twins; a CRP review-log (Appendix A/B/C) and SARIF are its human/machine twins — reconcile, don't fork.)*
7. **Runtime grounding (feature o11y + AI o11y — the territory edge)** — invariant 6 grounds findings in the
   *map* (docs/code, authoring-time). The circle only closes when they are also grounded in the *territory* (the
   running system). Two runtime signals feed the same SARIF finding-bus (the o11y→SARIF bridge is already routed):
   **feature o11y** (`observability/parity.py` compare-live) is *runtime verify-liveness* — a declared feature with
   no live emission is the deepest present-but-dead cell (the top of the liveness column); **AI o11y**
   (`costs/otel_metrics.py`) is the *measured* realization regime that fills REQ-19's seam (a planned-`$0` node with
   real LLM cost = a measured determinism regression). The generative fix reuses `scaffold_codegen/
   instrumentation_gen.py` (Harbor-proven — gap → generated instrumentation → the feature emits). This makes
   "verified" mean *"the feature emits a live signal proving it works, and here's what it cost"* — for the price of
   wiring, since every piece exists. Detail: `ANALYSIS_runtime-grounding-feature-and-ai-o11y.md`; wiring: `REQ-28`.

## 7. The roster

| Kit | Formalizes | Status | Origin |
|-----|------------|--------|--------|
| **det-req-kit** | the REQUIREMENT (FRs) | **SHIPPED** | 🔴 thin source (the origin) |
| **det-plan-kit** | the PLAN | **next** — grammar spec authored | 🟡 `$0` projection of REQ (schema already in det-req-kit §9) |
| **det-crp-kit** | the CONVERGENT REVIEW (focus + Appendix-A/B/C review-log) | **thin — grammar spec authored** (`SCHEMA_det-crp-0.1`) | 🟡 `$0` (compiler `new-cnvrg-rvw-prmpt` already runs; **no projector** — format+lint only) |
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
