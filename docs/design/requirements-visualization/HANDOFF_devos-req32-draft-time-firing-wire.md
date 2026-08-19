# Handoff → dev-os (det-req-kit + CRP-generator owner): wire REQ-32's draft-time firing seam

> **Cross-repo handoff, authored from startd8-sdk (emeritus direction).** REQ-32 is the convergence
> seam the whole det-doc-kit grammar batch fires through — but **5 of its 6 FRs land in dev-os / the
> skills tree, not the SDK.** This hands the dev-os `det-req-kit` + CRP-generator owner the build, with
> the reuse map, build order, and the honesty gate. **Spec:** `REQ-32-draft-time-firing-wire.md` (same
> dir). Per NR-6, landing FR-1/FR-2/FR-4 is the respective owner's call.

**Owner:** dev-os `det-req-kit` owner (FR-2/3/6) + CRP-generator/skills owner (FR-1) + PATTERN-CATALOG owner (FR-4).
**Home:** `~/Documents/dev/dev-os/` + `~/.claude/skills/new-cnvrg-rvw-prmpt/`.
**SDK-local slice:** FR-5 only (`startd8-sdk/docs/LOOP_CATALOG.md`) — can land in the SDK independently.

---

## 1. TL;DR — what to do

**Wire the firing seam ONCE; then every metabolized theme is one additive predicate.** Two ends:
1. **FR-1 (review end):** the CRP review-prompt generator injects a live *"settled corpus themes — do not
   re-derive"* block (from the census + catalog) into every generated prompt.
2. **FR-2 (draft end):** the det-req extractor fires the **fact-rung** theme lints as *advisory,
   exit-unchanged* findings in `collect_findings`.

Plus FR-3 (fact ships / judgment parks), FR-4 (complete the keyed lookup + `pattern_catalog sync`),
FR-5 (register LOOP_CATALOG #8). **All advisory, never blocking, never auto-applied. Reuse-only — no new engine.**

---

## 2. Why — "re-seeking dormancy" (the problem REQ-32 kills)

CRP-INDEX holds **7,299 accepted review suggestions**; four investigations metabolized the top ~1,700 into
concrete grammar rules. The corpus keeps **paying to re-derive the same settled concerns** review after
review, because a metabolized rule has **nowhere to fire**. That gap IS the dormancy. Wire the seam and
(a) each theme becomes one predicate (542 ambiguity re-derivations → one lint) and (b) the dormancy resolves
as a side effect. This is the KAIZEN "don't re-derive lessons" move for the review corpus.

---

## 3. Reuse map — what ALREADY exists (grounded 2026-08-19; do NOT rebuild)

The metabolization pipeline is built end-to-end and wired at the *routing* level (LOOP_CATALOG #7). **Only the
firing seam is missing.** REQ-32 connects these existing pieces:

| Piece | Lives (verified) | Role |
|-------|------------------|------|
| Census | `dev-os/scripts/render_crp_index.py` (`REVIEW_THEME_RULES`) | source of settled-theme counts |
| Catalog | `dev-os/PATTERN-CATALOG.md` + `contextcore learning pattern_catalog recall` | the recall store (PC-*) |
| Metabolizer | `/metabolize-finding` skill | finding → grammar rule |
| **Host** | `dev-os/det-req-kit/extract.py::collect_findings` (**`extract.py:964`**) | where lints fire |
| **Advisory-tier precedent** | `user_outcome_verify_advisory` (**`extract.py:780`**) + the advisory/error split (**`extract.py:1008`**) | FR-2 rides this exact exit-unchanged tier |
| Review-prompt generator | `~/.claude/skills/new-cnvrg-rvw-prmpt/SKILL.md` | FR-1 injects the block here |
| Precision gate | REQ-07 FR-7 (the 0-vs-2/2 false-positive data) | FR-3 parks judgment-rungs behind it |

---

## 4. Build order (FR → where it lands → dep)

1. **FR-4 — complete the keyed lookup + sync the catalog** *(do first — it's the prereq the others read).*
   Replace REQ-01 FR-4's prose "consult the base" with a `pattern_catalog recall` call at the reflective-loop
   draft slot; run `pattern_catalog sync` so PC-16..18 (+ successors) are in the recall store. **Touches:**
   `dev-os/REQ-01-Pattern-Promotion.md`, `dev-os/PATTERN-CATALOG.md`, `contextcore learning pattern_catalog`.
   **Verify:** `pattern_catalog recall` on a promoted theme returns it; REQ-01 FR-4 is no longer *Partial*.
2. **FR-2 — draft-surface wire.** Add the **fact-rung** theme lints as advisory findings in `collect_findings`,
   at the same exit-unchanged tier as `user_outcome_verify_advisory` (`extract.py:780/1008`). **Touches:**
   `dev-os/det-req-kit/extract.py`, `SCHEMA.md`, tests. **Verify:** a draft with a placeholder /
   open-enumeration / unresolved-binary marker yields the advisory finding; a clean draft yields none; **exit
   code unchanged either way.**
3. **FR-3 — the honesty gate (fact ships, judgment parks).** Only structural fact-rungs fire by default;
   semantic judgment-rungs are declared for column-completeness but execute nothing until they clear REQ-07's
   precision threshold on a labeled fixture set, and even then ship only as **dismissible candidates, never
   GAPs**. (The corpus's 0-vs-2/2 data says an ungated ambiguity heuristic false-fires like weak-verify.)
   **Verify:** a weasel-word/undefined-term draft yields no default finding; the parked tier surfaces it as an
   evidence-citing candidate, dismissible in one glance.
4. **FR-1 — review-surface wire.** Inject the settled-themes block, sourced **live from the census/catalog at
   generation time** (not a hand-copied snapshot), into every generated prompt. **Touches:**
   `~/.claude/skills/new-cnvrg-rvw-prmpt/SKILL.md`, `dev-os/CRP-INDEX.md`, `dev-os/PATTERN-CATALOG.md`.
   **Verify:** a generated prompt carries the block; regenerating after a catalog change reflects it.
5. **FR-5 — register LOOP_CATALOG #8** *(SDK-local — can land in startd8-sdk independently, see §7).*
6. **FR-6 — reuse-only additive guard.** The wiring imports the existing census/catalog/finding pieces (no new
   engine); a new theme = one predicate + one catalog row; the extractor's existing findings + exit codes are
   unchanged. **Touches:** `dev-os/det-req-kit/tests/test_theme_lints.py`.

---

## 5. ⚠️ Re-ground gate (this is a BELIEF artifact — bind before building)

Two hazards, per the cross-repo-handoff discipline:

1. **dev-os is on an in-flight branch touching exactly this area.** As of 2026-08-19 the dev-os primary tree is
   on **`chore/det-req-kit-learn-sdk-fields` @ `5431229`** — i.e. `extract.py` is being actively worked for the
   *grammar-field* thread. **Do NOT race it.** `git -C ~/Documents/dev/dev-os fetch` + check the branch state;
   layer FR-2/FR-3 on top of the committed field work, don't fork it.
2. **Verify the citations against the live tree before coding.** The `extract.py:764/780/964/1008` line numbers
   and the `PC-16..18` sync status were grounded on 2026-08-19 but drift. Confirm `collect_findings`, the
   advisory/error split, and whether `pattern_catalog recall`/PC-16..18 are already synced (FR-4 may be partly
   done on the chore branch) before adding predicates.

---

## 6. Done-when (exit criteria)

- [ ] `pattern_catalog recall` returns a promoted theme (PC-16..18); REQ-01 FR-4 no longer *Partial* (FR-4).
- [ ] A fact-rung marker in a draft yields an advisory finding; clean draft none; **exit code unchanged** (FR-2).
- [ ] Judgment-rungs fire **nothing** by default; the parked tier surfaces evidence-citing, dismissible
      candidates, never GAPs (FR-3).
- [ ] Every generated review prompt carries a live settled-themes block; a catalog change is reflected (FR-1).
- [ ] LOOP_CATALOG #8 registered, moving number = re-seek rate, scoped cross-kit (FR-5).
- [ ] Adding a new theme = one predicate + one catalog row; existing extractor findings/exit unchanged (FR-6).

---

## 7. The SDK-local slice you can land now (FR-5)

FR-5 is the one piece that lives **here**: register the census→promote→metabolize→lint→re-census loop as
**LOOP_CATALOG #8 (Review-Theme Metabolizer)** in `startd8-sdk/docs/LOOP_CATALOG.md`, moving number = *re-seek
rate for a metabolized theme*, scoped as a cross-kit family capability (not det-req-kit-only). It plants the
flag + gives the loop a home while FR-1–4/6 are built in dev-os. This handoff's author can land FR-5
independently on request.

---

## 8. Pointers

- **Spec:** `REQ-32-draft-time-firing-wire.md` (6 FRs, det-req/0.1, this dir).
- **Synthesis it derives from:** `SYNTHESIS_crp-theme-metabolization-four-investigations.md` (§1 convergence,
  §4 the two wires) + `SYNTHESIS_crp-other-and-cli-mining.md` (the grammar-field batch it unblocks).
- **The batch it prerequisites:** `Depends:` (G-1, biggest demand) · `Emits:` (REQ-30) · `Lifecycle:` (REQ-31)
  · `Config:`/`Provenance:`/`Budget:` — each one predicate through this seam once it's wired.
- **Precedent to mirror:** REQ-22/23 (fact-cells), REQ-25 (fact-rung/judgment-rung), REQ-07 (precision gate).

*Cross-repo handoff authored from startd8-sdk, 2026-08-19. Re-ground against the live dev-os tree (§5) before
build. The SDK's role ends at authoring this direction + optionally landing FR-5 (NR-6).*
