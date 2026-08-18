# Master next steps — the NLPS effort (detailed)

**Date:** 2026-08-17 · **Type:** master handoff / roadmap · **Scope:** the entire session arc
(Node-IR → realization → retrospective → liveness → det-doc-kit family → o11y grounding → research agenda)
**Sub-docs:** `NEXT_STEPS_det-doc-kit-family-effort.md` (family build) · `RESEARCH_AGENDA_open-threads-across-the-nlps.md`
(research) · `HANDOFF_build-REQ-29-projector-and-pilot.md` (the immediate build) · `CHARTER_det-doc-kit-family.md` (the invariants).
**Owner of direction:** emeritus session (complete) · **Owner of build:** build sessions · **Owner of cross-repo:** the respective kit/repo owners + you.

## 0. Where the effort stands — one paragraph

> **Reconciled 2026-08-18 — the det-doc-kit family is no longer "spec'd", it's BUILT.** This session shipped
> **three working `$0` projectors** (det-plan `plan_codegen`, det-handoff `handoff_codegen`, det-howto
> `howto_codegen` — built independently from the STANDARD), the **det-crp format+lint kit** (`crp_lint`), the
> extracted+**independently-replicated** `STANDARD_det-doc-kit-projector-pattern.md`, and `scripts/verify_ledger.py`.
> §1/§2/§6/§7 below are updated; the old "build REQ-29 first" is DONE. Verify the greens with `verify_ledger.py`.

The NLPS document layer is formalized end-to-end on paper AND the family's SDK-side realization is built: a
`$0`-derivation cascade from a human-gated requirement to code, bracketed by two human bookends, findings-grounded
in both the **map** (SARIF) and the **territory** (feature/AI o11y). The **Node-IR arc** (REQ-16→24) is *built*;
the **det-doc-kit family** (3 projectors + crp lint + a proven standard) is *built SDK-side*; the **liveness column**
is *spec'd/partly-built*; the **research→spec pipeline** resolved most open questions into REQs. What remains is the
**cross-repo kit-dir adoption** (dev-os), the **grammar-field batch** (REQ-30/31/32 + `Depends:` G-1), and the
**card-browse UX arc** (Move 3 shipped; search + Move 2 next).

## 1. Full-arc state table

| Artifact | What | State | Next action |
|----------|------|-------|-------------|
| **ADR** promote oracle+gate | verify/approve/was → Node fields | ✅ accepted · ✅ built (REQ-16/17) | — |
| **REQ-16/17** | derivation edge (+ reserved `regime` slot) · verify/approve/was fields | ✅ **built** (`aaa39178`) | — |
| **REQ-18/19** | realization regime (declared → measured seam) | ✅ **built** | feed the realization-facet REQ (below) |
| **REQ-20/21/24** | Lesson node + `revises` edge · guarded auto-tier · byte-identity applier | ✅ **built** | — |
| **REQ-22/23** | verify-liveness · liveness fact cells | ✅ **built** | — |
| **REQ-25** | liveness hypothesis cells (fact-rungs ship, judgment-rungs park) | 📄 spec · build-ready | build (Spec Delivery Loop) |
| **REQ-26** | a11y as a cross-topology lens (the FF-1 analogue) | ✅ **built** (`c8745e5d`; `render_a11y.a11y_view_of_nodes` + `_a11y_shell`) — v0.2 reflective correction: a11y is a modality that COMPOSES with node_lenses, not a lens value inside it; `--format a11y` × `--renderer tree\|graph` + `diff --a11y`; 10 FR pins | — |
| **REQ-27** | self-dogfood `verify.gate` on our own corpus | 📄 spec · build-ready | build |
| **REQ-28** | runtime o11y grounding (feature + AI o11y → SARIF/seam) | 📄 spec · build-ready | build |
| **REQ-29** | the `$0` REQ→PLAN projector (det-plan-kit's generator) | ✅ **built + HTH-hardened** (`35e75c89`; `plan_codegen`) | — (extracted the STANDARD below) |
| **det-handoff projector** | the `$0` REQ+ledger→HANDOFF projector (2nd projector) | ✅ **built** (`5ba7eb48`; `handoff_codegen`) — adoption gate PASSED | — |
| **det-howto projector** | the `$0` REQ→HOWTO command-reference (3rd projector) | ✅ **built INDEPENDENTLY** (`2baf4de0`; `howto_codegen`) — replication gate PASSED | — |
| **STANDARD** det-doc projector pattern | the 5-part shape + Part-6 + §0 + golden-diff method | ✅ **extracted + INDEPENDENTLY REPLICATED** | governs projectors 4+ (det-ledger) |
| **verify_ledger.py** | mechanized done-census (UNLANDED/PHANTOM) | ✅ **built** (`72fdd740`) | wire into CI (optional) |
| **REQ-32** | the draft-time firing wire (the convergence unlock — 2 wires + REQ-01 FR-4 + LOOP_CATALOG #8) | 📄 **spec** · build-ready | build (cross-repo: dev-os + CRP generator) — **prereq for the theme lints** |
| **REQ-30/31** | schema `Emits:` · lifecycle `Lifecycle:` FR-field grammar (themes #3/#6) | 📄 **specced** (`REQ-30-schema-emits-field.md` · `REQ-31-lifecycle-field.md`) | build after REQ-32's firing seam (cross-repo det-req-kit) |
| **ambiguity / atomic-write / security fact-rungs** | the top-3 ship-ready theme lints | ⬜ backlog (SYNTHESIS §3) | author each as one predicate once REQ-32's seam exists |
| **CHARTER** det-doc-kit family | 7 invariants + audit-hardened §5 | ✅ directed | governs every kit build |
| **SCHEMA** det-plan/0.1 · det-handoff/0.1 · det-howto/0.1 · det-crp/0.1 | the four formats | ✅ **authored + hardened** (SDK design corpus) | adopt into `dev-os/det-*-kit/` dirs (cross-repo) |
| **realization-facet REQ** | fill the reserved `regime` slot + determinism-% rollup | ⬜ **not yet specced** | spec it (folds OQ-1/OQ-4) |
| **det-crp-kit** | thin: focus + review-log schemas + `crp_lint.py` | ✅ **format + lint BUILT** (`SCHEMA_det-crp-0.1` · `crp_lint`, `639dea4b`; dogfooded clean over 26 docs) | adopt the kit dir into dev-os |
| **det-req-kit cleanup** | relocate 8 process docs; one shared SARIF renderer | ✅ flagged (`dev-os` commit `5431229`) | det-req-kit owner |

## 2. Build backlog — detailed, dependency-ordered

### 2.1 REQ-29 — the det-plan projector ✅ DONE (and the whole projector family with it)
- **BUILT + HTH-hardened** (`35e75c89` → `72fdd740`): `plan_codegen` + the five-pilot golden-first run + the
  `/reflective-adoption` fold-back into `det-plan/0.1` (G-1/G-2/G-3). Then the arc continued *past* REQ-29:
  the **STANDARD** was extracted (retrospective), **det-handoff** adopted it (gate passed), **det-howto** was built
  **independently** from the standard alone (replication gate passed), and **det-crp** got its **format+lint**
  (`crp_lint`). The one open det-doc tail: **cross-repo kit-dir adoption into dev-os** (§2.2) + the grammar-field
  batch (below). Pilot/standard/report all in the SDK design corpus. **Nothing here is "next" — it's shipped.**

### 2.2 det-plan-kit dev-os dir (cross-repo, after 2.1)
- Adopt `SCHEMA_det-plan-0.1` → `dev-os/det-plan-kit/SCHEMA.md` + `plan.schema.json` + `extract.py` (imports the one
  SARIF renderer) + `templates/` + `examples/` + `tests/`. **No `new.py`, no finding→plan-stub.** Kit-owner coordination.

### 2.3 The liveness column + o11y (parallel-safe, independent)
- **REQ-25** (hypothesis cells) · **REQ-28** (runtime o11y) — both spec'd, build-ready, advisory, reuse-only. Extend
  the shipped REQ-22/23 fact cells; independent of the det-plan work.

### 2.4 The renderer/lens + corpus-hygiene (independent)
- **REQ-26** (a11y-as-lens — the FF-1 analogue; highest-leverage empty cell) · **REQ-27** (self-dogfood `verify.gate`).

### 2.5 The realization-facet REQ (needs a spec first)
- Fill the reserved `regime` slot (REQ-16) with edge-carried realization; derive node realization; **determinism-%
  rollup**; enforce invariant 9. **Spec it folding OQ-1 (planned-vs-realized delta) + OQ-4 (rollup semantics)** from
  the research agenda. Deps built (REQ-18/19).

### 2.6 det-crp-kit ✅ format + lint BUILT (SDK-side)
- **DONE** (`639dea4b`): `SCHEMA_det-crp-0.1` (focus + Appendix-A/B/C review-log schemas) + `crp_lint`
  (`src/startd8/crp_lint/` + `scripts/crp_lint.py`), citing `new-cnvrg-rvw-prmpt` as the `$0` compiler (no
  projector — thin format+lint). **Dogfooded clean over the 26-doc corpus.** Fold-back: id-uniqueness is
  authoring-time not lint-time (references ≠ duplicates); header checks conditional-on-presence. Remaining:
  adopt the kit dir into `dev-os/det-crp-kit/` (cross-repo) + work the 213 weak-Appendix review-logs the
  `dev-os/CRP-INDEX.md` census flagged (the lint's real backlog).
- **Grounded in `dev-os/CRP-INDEX.md`** (the findings-half twin of the reflective-pairs index): 1033 review-logs +
  33 saved prompts = the corpus; strong/medium/weak Appendix conformance (802/243/**213 weak** = `crp_lint`'s backlog).
  Cite it in the spec exactly as det-plan cites reflective-pairs. See `ANALYSIS_crp-index-review-wisdom-into-grammar.md`.

## 3. Research backlog — detailed (from `RESEARCH_AGENDA_*`)

**Research-now (emeritus lane, unblocked):**
1. **CRP-theme metabolization** 🥇 — ✅ **INVESTIGATED (four parallel agents, 2026-08-17)** → `SYNTHESIS_crp-theme-metabolization-four-investigations.md`. Mined the top ~1,700 of 7,299 accepted suggestions (themes #2 ambiguity · #3 schema · #6 lifecycle · error/security/concurrency/determinism) into concrete fact/candidate-split `extract.py` lints. **THE CLASS (ATM Phase-1.5 convergence):** all four themes land at ONE seam — the *draft-time firing wire* — whose absence IS the re-seeking dormancy (thread #5). **Ship-ready backlog:** (1) ambiguity fact-rungs (placeholder/open-enum/unresolved-binary — 542 rows, near-1.0 precision, reuses `user_outcome_verify_advisory`); (2) concurrency atomic-write lint (lowest-FP); (3) security mitigation-vocab lint (reuses REQ-25 `verify_file`); (4) **REQ-30/REQ-31** = schema `Emits:` + lifecycle `Lifecycle:` fields; park all judgment-rungs per REQ-07 FR-7. **The fix = two wires** (CRP-prompt injection + `extract.py` content-lints) + complete `REQ-01 FR-4` + `pattern_catalog sync`; proposed **LOOP_CATALOG #8** (cross-kit family). *(Continues the proven REQ-22/23 method — themes #1/#4 already metabolized.)*
2. **Concept-embedding mining** — re-mine the 6 corpora by *meaning* not keyword (kaizen scored 0% on grounding
   despite being about it); would honestly re-measure the Craft-Grammar claim. ✅ **PARTLY EXECUTED (2026-08-18)** on the CRP corpus → `SYNTHESIS_crp-other-and-cli-mining.md`: mined the "other" bucket (3,772 rows/52%) + the missed CLI theme (315). **Quantified the keyword bias:** 4 existing themes undercounted 30–150 rows each (determinism true reach ~2.5×; ambiguity 542→~700), fixable by a $0 one-file keyword-add to `render_crp_index.py`. **Found 3 new metabolizable themes** in "other": dependency-ordering (388/192 — validates the open `Depends:` field G-1), provenance/source-of-truth (159/114 → `Provenance:`), cost/budget (134/89 → `Budget:`). CLI = 74% metabolizable → `Config: precedence=` field (grounded in the shipped `env > CLI` bug). ~45% of "other" is correctly-absent one-off noise. **Feeds the grammar-field batch** (below). Residual: extend to the other 5 corpora (legal/benchmark/household/dev-os/kaizen).
3. **Two-IR twin reconciliation** — a note reconciling Lesson↔SARIF + CRP-log↔SARIF onto one findings representation,
   *before* det-crp-kit + the retrospective build fork it.
4. **Cross-corpus universality** — extend the grammar census to legal + benchmark + household (universal vs local).
5. **The re-seeking dormancy** — ✅ **DIAGNOSED (2026-08-17, Investigation D):** verdict = **DORMANT, worse than stated** — the "Phase 4.5/4.6 keyed lookup" the analysis assumed exists is **not in the CRP path at all**; it's an unbuilt reflective-loop hook (`REQ-01 FR-4`, *Partial*), and `PATTERN-CATALOG` PC-16..18 self-report "not yet wired as a draft-time check." **It is the SAME missing wire as thread #1's convergence** — fix them together (the two wires in the SYNTHESIS §4). Also found: the general metabolizer is **not bespoke** — it already exists in assembled form (census + catalog + `/metabolize-finding` + `extract.py`), wired at routing by LOOP_CATALOG #7; only the firing seam is missing.

**Fold-into-a-REQ:** OQ-1/OQ-4 → the realization-facet REQ (§2.5) · OQ-R4/R6 → the general retrospective-bridge.
**Watch:** convention-promotion tracking — re-census after the next corpus.

## 4. Cross-repo & owner handoffs — detailed

| Item | Where | State | Owner / action |
|------|-------|-------|----------------|
| det-req-kit cleanup | `dev-os/FINDING-det-req-kit-format-dir-accretion.md` | committed (`5431229`) on `chore/det-req-kit-learn-sdk-fields` | det-req-kit owner — relocate 8 process docs; consider one shared SARIF renderer |
| NODE-SCHEMA §1 refresh | `dev-os/NODE-SCHEMA.md` | ADR accepted | add verify/approve/was + fix the §1↔code staleness |
| ContextCore Node mirror | ContextCore | pending | adopt the 0.4.0 fields |
| det-plan/det-crp kit dirs | `dev-os/` | pending | create per charter §5 (essentials-only) |
| Push local `main` → `origin` | startd8-sdk | 116 ahead / 14 behind | **your call** — the coordinated publish decision (`PUBLISH_navigator-subsystem-to-origin.md`), not a mechanical merge |

## 5. Invariants every build must carry (the non-negotiables)

- **Two bookends stay prose** — no kit for INTENT/ADR/RESEARCH (front) or RETROSPECTIVE/§0 (back); `(req, PROJECTOR)`
  is a correct-absence.
- **Own a format, never a generator** (Mottainai — cite, don't restate).
- **The §5 mirror-inertia checklist** — format-essentials only; source-kit vs derived-kit; reuse-not-vendor SARIF;
  kit dir = format-only. *Audit the source before mirroring.*
- **Liveness stratifies by altitude** — FR-gate → REQ-verify → PAIR-companion → corpus → RUNTIME. Count LIVE only.
- **`$0`/never-inferred** · **anti-inflation** (projected artifact starts `0.1`) · **propose-don't-dispose** at every generative seam.
- **Byte-identical** default render · **advisory not blocking** for every liveness/o11y check · **absence-vs-error** (never read absent as 0).

## 6. The critical path (reconciled 2026-08-18 — the projector spine is BUILT)

```
✅ det-doc-kit SDK spine BUILT: det-plan → STANDARD → det-handoff → det-howto (indep) + det-crp (format+lint)
   remaining forks (all independent, none blocked by the above):
   ├─ grammar-field batch: REQ-32 draft-time firing wire → REQ-30/31 (Emits:/Lifecycle:) + `Depends:` G-1
   │     (cross-repo: det-req-kit grammar; G-1 makes det-plan's dependsOn REAL) — HIGHEST strategic leverage
   ├─ card-browse UX: Move 3 ✅ shipped → search (consumes Move 3's seam) → Move 2 (audience tiers)
   ├─ cross-repo kit-dir adoption: dev-os/det-{plan,handoff,howto,crp}-kit/ (essentials-only, charter §5)
   ├─ liveness + o11y: REQ-25 residual · REQ-28 · whole-liveness-layer govern wiring
   ├─ REQ-26 (a11y-as-lens) · REQ-27 (self-dogfood verify.gate) · realization-facet REQ (spec first)
   └─ Cross-repo (owners): NODE-SCHEMA §1 · ContextCore mirror · origin-push (your call)
```

## 7. If you do ONE thing next (reconciled 2026-08-18)

The old "build REQ-29" is **done** (+ the whole projector family). The current highest-leverage picks:

- **Strategic:** the **grammar-field batch** — **REQ-32** (the draft-time firing wire every metabolized theme queues
  at) then **REQ-30/31** (`Emits:`/`Lifecycle:`) + **`Depends:` G-1**. G-1 makes the det-plan projector's `dependsOn`
  *real* (empty today), and the four fields share one firing seam. Cross-repo (det-req-kit grammar) — owner coordination.
- **Clean in-repo pickup:** **search** (`REQ-freetext-search-on-navigator-card-browse`) — Move 3 shipped its seam, so
  search's FR-5 collapses to "register `srch-hidden`" (the paging bug is already fixed). BUILD-READY, S–M.
- **Research lane:** extend **concept-embedding mining** to the other 5 corpora (the CRP corpus is done, 2026-08-18).

**The one-line close:** *the det-doc-kit projector family is built and proven by independent replication; what's left
is the cross-repo kit-dir adoption, the grammar-field batch that makes the projections richer, and the card-browse UX
arc — all independent, none blocked. Verify the greens with `verify_ledger.py`, not this list.*
