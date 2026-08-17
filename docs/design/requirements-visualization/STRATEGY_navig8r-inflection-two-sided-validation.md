# Strategy — navig8r at the inflection: the two-sided validation surface

**Written:** 2026-08-17 · **Scope:** the requirements-visualization navigator (navig8r), its strategic
direction after the distillation + detail-view + variant-inventory session. **Status:** direction of
record; Move 3 is specced BUILD-READY, Moves 2–1 outlined as the next rungs.

---

## 0. The thesis — navig8r is a two-sided coin

navig8r is not "a requirements viewer." It is **the validation surface** where a human confirms a body
of requirements is *simultaneously*:

1. **Technically sound** — *"verification that cannot silently die."* Grounding, liveness, provenance,
   the verify-oracle. *Is the work correct / grounded / actually built?* (the REQ-18..25 liveness/
   realization layer, the signal strip's grounding, the band's risk→FR coverage.)
2. **Business-valuable** — a human can **readily navigate** the requirements and **validate they are of
   high value.** *Is this worth building? Is it the right thing?* (the card readability, detail peek,
   full-page view, doc-context band, free-text search, and above all the **audience tiers**.)

**These are two sides of one coin, not two features.** The same surface must let an auditor validate
grounding *in depth* and an exec validate value *at a glance* — which is precisely why **audience is the
organizing axis**, and why the readability work this session is strategic, not cosmetic. Reducing navig8r
to only the technical side is a mis-scoping.

Everything below serves this coin. The **cross-repo destiny** (navig8r renders legal / benchmark / dev-os
node corpora, not just requirements) is the same coin at scale: each repo needs both validations for its
own audiences.

---

## 1. The inflection — from one renderer to a system

This session did three things whose sum is a turning point: it **distilled** accidental complexity (the
structure→string→structure fields reparse — the *data*-layer distillation), **added depth** (detail peek +
full-page `#<key>` route + deep-linking + doc-context band), and **mapped the space** (the
`SOURCE × TOPOLOGY × PRESENTATION × AUDIENCE` variant inventory — six renderers as distinct cells).

Grounded signals that navig8r has outgrown "a card renderer":

| Signal | Measured | What it says |
|--------|----------|--------------|
| Renderers cross-link | **0** card→graph/diff/a11y hrefs | six *siloed* CLI outputs, not a system |
| Audience axis on new surfaces | **24** lens refs exist, **0** tier the band/detail/search | the value-validation axis is under-built |
| Interaction file size | `_template.py` = **1408 lines**, **83** visibility-toggle refs | a god-file; composition is ad-hoc |
| Filter composition | `pagedCards()` ignores `pf-hidden` (a real bug) | status ∧ paging **don't compose** today |

The honest tension: this session we **both distilled and accreted** (~700 new lines of band/detail/route
into the same 1408-line file). Velocity is re-growing the complexity the distillation removed; the
pagedCards bug is that composition breaking under the weight.

---

## 2. The three moves (in sequence)

### Move 3 — Distill the interaction layer into composable predicates  *(the enabler; do first)*
**Problem (grounded):** card visibility is a conjunction of independent predicates (`status ∧ search ∧
page ∧ audience-lens`), but each is an ad-hoc hide-class toggled by its own handler with no single
composition point — so they don't intersect (the `pagedCards`↔`pf-hidden` bug).
**Move:** one `applyVisibility()` recompute point; each filter owns its own non-clobbering hide-reason;
`pagedCards()` pages the **survivor set** (fixes the bug); a documented **seam** future predicates plug
into. Behaviour-preserving except the bug fix; profiled-only; app-path byte-identical.
**Serves the coin:** the *enabler* for both sides — audience-tiering (value) and search (navigation) can't
compose cleanly until this lands. **Also kills a real defect.**
**Status:** **specced BUILD-READY** — `REQ-unify-card-visibility-predicates.md` (7 FRs) + handoff. It is
the *interaction*-layer twin of this session's *data*-layer distillation (`ce6ed667`).

### Move 2 — Make audience a first-class, systematic tier  *(highest value; rides on Move 3)*
**Problem (grounded):** the fluency/role lens exists but **0** of the new surfaces tier by it; we keep
building *maximal-then-deferring* (the doc-context band this session).
**Move:** every surface **declares its audience tiers**, resolved by the existing lens — exec/beginner sees
minimal (criticality · counts · risk summary), auditor sees maximal (+ trust · data · version · full
risk detail). The deferred band-pare becomes a lens tier, not a delete.
**Serves the coin:** this *is* the human/business-value side — the right person validates the right thing
at the right depth. The most untapped leverage (the other three axes are heavily built).
**Status:** outlined; **reflectively specced against Move 3's landed code** (audience becomes one more
predicate/lens on the unified visibility model — spec it *after* Move 3 so it grounds against the real
seam, not an imagined one).

### Move 1 — navig8r as the hub (topology cross-links)  *(the vision; incremental)*
**Problem (grounded):** **0** cross-links — the six renderers are chosen upfront by a `--renderer` flag.
**Move:** enter the card browse and **pivot** — each requirement's full-page view links to its **graph**
node, its **diff**, its **a11y** leaf, its **corpus-index** row. The full-page `#<key>` route built this
session is the anchor; cross-links are additive.
**Serves the coin:** navigation across *both* validations — the technical shape (graph/diff/liveness) and
the value read (card/detail) — from one entry point.
**Status:** outlined; specable against current code (the target renderers + the full-page route all exist);
sequence last — it's the least urgent and most incremental.

---

## 3. Sequencing & dependencies

```
Move 3 (unify visibility predicates)  ── enabler, fixes pagedCards ──┐
                                                                     ├──► Move 2 (audience tiers)  ──► Move 1 (hub cross-links)
REQ-freetext-search (already BUILD-READY) ── consumes Move 3's seam ─┘
```

- **Move 3 SUBSUMES the search REQ's FR-5** (both fix `pagedCards`). Land **Move 3 first**, then the
  search delivery consumes the unified `applyVisibility` seam (its `srch-hidden` becomes one predicate)
  rather than re-patching paging. Loop order: **Move 3 → search → Move 2 → Move 1.**
- Each move is delivered by a **separate implementation session via the Spec Delivery Loop** (the loop
  operator), not inline here. Move 3's spec + `HANDOFF_take-REQ-unify-visibility-predicates-through-the-loop.md`
  are the pickup.
- **Move 2 and Move 1 are specced *when their turn comes*, reflectively against the *landed* code** — not
  pre-authored here — so their §0 planning-insights ground against reality (the reflective-requirements
  discipline), especially Move 2 against Move 3's actual seam.

---

## 4. Why this is the right bet

- It **fixes a real bug** on the way (pagedCards), so Move 3 pays for itself immediately.
- It **stops the god-file accreting** — every future filter/lens/surface composes by construction.
- It **unlocks the under-built axis** (audience) that most directly serves the *value-validation* side of
  the coin — the user's stated "broadest audience, lowest-common-denominator across levels of expertise."
- It **compounds cross-repo**: composable predicates + audience tiers + a hub generalize to any NODE-SCHEMA
  corpus (legal/benchmark/dev-os), where both validations must serve different audiences.

*Direction of record. Move 3 is BUILD-READY; take it through the loop, then re-spec Move 2 against its
landed seam.*
