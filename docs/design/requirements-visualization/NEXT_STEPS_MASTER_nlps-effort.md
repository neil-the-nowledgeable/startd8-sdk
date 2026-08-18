# Master next steps — the NLPS effort (detailed)

**Date:** 2026-08-17 · **Type:** master handoff / roadmap · **Scope:** the entire session arc
(Node-IR → realization → retrospective → liveness → det-doc-kit family → o11y grounding → research agenda)
**Sub-docs:** `NEXT_STEPS_det-doc-kit-family-effort.md` (family build) · `RESEARCH_AGENDA_open-threads-across-the-nlps.md`
(research) · `HANDOFF_build-REQ-29-projector-and-pilot.md` (the immediate build) · `CHARTER_det-doc-kit-family.md` (the invariants).
**Owner of direction:** emeritus session (complete) · **Owner of build:** build sessions · **Owner of cross-repo:** the respective kit/repo owners + you.

## 0. Where the effort stands — one paragraph

The NLPS document layer is formalized end-to-end on paper: a `$0`-derivation cascade from a human-gated
requirement to code, bracketed by two human bookends, findings-grounded in both the **map** (SARIF) and the
**territory** (feature/AI o11y). The **Node-IR arc** (REQ-16→24) is *built*; the **liveness column** and the
**det-doc-kit family** are *spec'd*; the **research→spec pipeline** resolved most open questions into REQs, leaving
a small themed research backlog. What remains is **building** (out of the emeritus lane) and a few **cross-repo
coordinations** (owners' calls).

## 1. Full-arc state table

| Artifact | What | State | Next action |
|----------|------|-------|-------------|
| **ADR** promote oracle+gate | verify/approve/was → Node fields | ✅ accepted · ✅ built (REQ-16/17) | — |
| **REQ-16/17** | derivation edge (+ reserved `regime` slot) · verify/approve/was fields | ✅ **built** (`aaa39178`) | — |
| **REQ-18/19** | realization regime (declared → measured seam) | ✅ **built** | feed the realization-facet REQ (below) |
| **REQ-20/21/24** | Lesson node + `revises` edge · guarded auto-tier · byte-identity applier | ✅ **built** | — |
| **REQ-22/23** | verify-liveness · liveness fact cells | ✅ **built** | — |
| **REQ-25** | liveness hypothesis cells (fact-rungs ship, judgment-rungs park) | 📄 spec · build-ready | build (Spec Delivery Loop) |
| **REQ-26** | a11y as a cross-topology lens (the FF-1 analogue) | 📄 spec · build-ready | build |
| **REQ-27** | self-dogfood `verify.gate` on our own corpus | 📄 spec · build-ready | build |
| **REQ-28** | runtime o11y grounding (feature + AI o11y → SARIF/seam) | 📄 spec · build-ready | build |
| **REQ-29** | the `$0` REQ→PLAN projector (det-plan-kit's generator) | 📄 spec · **has build handoff** | **build first** (§2.1) |
| **CHARTER** det-doc-kit family | 7 invariants + audit-hardened §5 | ✅ directed | governs every kit build |
| **SCHEMA** det-plan/0.1 | the plan format | 📄 spec | adopt into `dev-os/det-plan-kit/SCHEMA.md` |
| **realization-facet REQ** | fill the reserved `regime` slot + determinism-% rollup | ⬜ **not yet specced** | spec it (folds OQ-1/OQ-4) |
| **det-crp-kit** | thin: version focus + review-log schemas + `crp_lint.py` | ◐ assessed · ⬜ not specced | spec it |
| **det-req-kit cleanup** | relocate 8 process docs; one shared SARIF renderer | ✅ flagged (`dev-os` commit `5431229`) | det-req-kit owner |

## 2. Build backlog — detailed, dependency-ordered

### 2.1 REQ-29 — the det-plan projector (BUILD FIRST) 🥇
- **Why first:** all deps built (`det_req`/`queue`/`realization`/`findings_sarif`); the format (`SCHEMA_det-plan-0.1`)
  is authored; the demand is grounded (26 companionless REQs); it's the det-doc-kit family's first realized member.
- **Runbook:** `HANDOFF_build-REQ-29-projector-and-pilot.md` — 8 FRs, the **five-pilot golden-first matrix**
  (REQ-08 + REQ-01 golden-parity · REQ-03 negative-gate · REQ-16/17 demand), the golden-diff fold-back method.
- **Guards:** `$0`/never-inferred · charter §5 essentials-only (import `findings_sarif`, no `new.py`/vendor/process-docs).
- **Deliverable:** the projector + the pilot report (the two golden deltas + dispositions) = the reflective-adoption fold-back into `det-plan/0.1`.

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

### 2.6 det-crp-kit (needs a spec first — now census-grounded)
- Thin: version the focus-file + Appendix-A/B/C review-log schemas out of the agent guide; add `crp_lint.py`; **cite**
  `new-cnvrg-rvw-prmpt` as the `$0` compiler. Complements det-plan (the mirror-asymmetric cell).
- **Grounded in `dev-os/CRP-INDEX.md`** (the findings-half twin of the reflective-pairs index): 1033 review-logs +
  33 saved prompts = the corpus; strong/medium/weak Appendix conformance (802/243/**213 weak** = `crp_lint`'s backlog).
  Cite it in the spec exactly as det-plan cites reflective-pairs. See `ANALYSIS_crp-index-review-wisdom-into-grammar.md`.

## 3. Research backlog — detailed (from `RESEARCH_AGENDA_*`)

**Research-now (emeritus lane, unblocked):**
1. **CRP-theme metabolization** 🥇 — `/audit-then-metabolize` on `CRP-INDEX.md`'s 7299 accepted suggestions: mine the
   recurring themes, metabolize the top *un-metabolized* one into a det-req/det-plan grammar rule so drafts satisfy it
   and reviews stop re-deriving it (shift-left). **Top pick: an "ambiguity" lint** (theme #2 — 158 docs, 542 rows).
   *(We already metabolized themes #1 verify + #4 observability into REQ-22/23 — this continues the proven method.)*
   See `ANALYSIS_crp-index-review-wisdom-into-grammar.md`.
2. **Concept-embedding mining** — re-mine the 6 corpora by *meaning* not keyword (kaizen scored 0% on grounding
   despite being about it); would honestly re-measure the Craft-Grammar claim.
3. **Two-IR twin reconciliation** — a note reconciling Lesson↔SARIF + CRP-log↔SARIF onto one findings representation,
   *before* det-crp-kit + the retrospective build fork it.
4. **Cross-corpus universality** — extend the grammar census to legal + benchmark + household (universal vs local).
5. **The re-seeking dormancy** — investigate why `PATTERN-CATALOG`/the Phase-4.5 lookup under-fuels draft-time (a
   dormant cross-doc-memory value path; feeds the retrospective/metabolize loop).

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

## 6. The critical path

```
REQ-29 (build) ──▶ det-plan-kit dev-os dir ──▶ det-crp-kit (spec+build)
   │  (parallel, independent of the above)
   ├─ REQ-25 · REQ-28 (liveness + o11y builds)
   ├─ REQ-26 · REQ-27 (lens + self-dogfood)
   └─ realization-facet REQ (spec folding OQ-1/4) ──▶ build
Research (parallel): concept-embedding · twin-seam note · cross-corpus universality
Cross-repo (owners): det-req-kit cleanup · NODE-SCHEMA §1 · ContextCore mirror · kit dirs · origin-push (your call)
```

## 7. If you do ONE thing next

**Build REQ-29** (the det-plan projector) via its handoff — it's the family's first realized member, fully
grounded, with a golden-first pilot set whose deltas *are* the reflective-adoption fold-back. It turns the whole
det-doc-kit family from paper into a running `$0` generator, and its pilot immediately hardens `det-plan/0.1`.

**If you'd rather research than build:** point one agent at **concept-embedding mining** — it re-measures the
Craft-Grammar claim (the cross-repo thesis's foundation) honestly, beating the vocabulary bias, and it's a clean
one-agent pickup with a ready prompt in the research agenda.

**The one-line close:** *everything analyzed this session is built, spec'd-with-a-handoff, or on a grounded research
thread with a named next-agent — nothing scattered, nothing lost; the loop is closed on paper and waits only on hands.*
