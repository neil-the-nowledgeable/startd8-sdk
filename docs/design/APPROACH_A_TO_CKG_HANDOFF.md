# Approach A → CKG Knowledge Provider — Hand-off Note

**Date:** 2026-06-01
**From:** session `5398ab72` (RUN-011 remediation track)
**To:** the CKG / Code-Observability track (worktree `feat/ckg-phase1`)
**Status:** Hand-off — the standalone `APPROACH_A_PROJECT_KNOWLEDGE_{REQUIREMENTS,PLAN}.md`
are **superseded by `CODE_KNOWLEDGE_GRAPH_DESIGN.md` §8.1** ("Knowledge Provider = Approach A,
done right"). This note salvages only the deltas worth folding into the CKG Knowledge
Provider spec; everything else in those docs is subsumed by CKG and should be ignored.

---

## Why this note exists (not a turf claim)

While remediating RUN-011 (M4 field/path invention), this session drafted a standalone
"Approach A" requirements + plan + CRP — *before* discovering that CKG Phase 1 had already
shipped past the tree-sitter pin-conflict blocker and that the CKG design explicitly owns
Approach A as its L5 Knowledge Provider. The bespoke `ProjectKnowledge` regex producer it
specified (S1/S2) would **duplicate** CKG's resolved model, `tsconfig_paths.py`,
`cross_file_imports.py`, and Prisma DMMF (deferred/optional in CKG) — exactly the "build it
twice" outcome `CROSS_FILE_CONTRACT_RESOLUTION.md` §11 warned against. So the *producer* is
dropped. *(Nits corrected per the CKG session's hand-off review: the shipped import-resolution
file is `cross_file_imports.py`, not `import_resolution.py`; DMMF is deferred/optional, not
"planned".)*

What survives is a short list of points that went through a convergent review (CRP R1) and
**strengthen the Knowledge Provider regardless of substrate (SCIP vs draft-mode resolver).**
Treat these as review input to CKG's Phase-2 Knowledge-Provider spec, accept/reject as the
CKG track sees fit.

---

## The salvageable deltas (4)

### D1 — Injection ≠ adherence: measure adherence empirically, don't binary-gate it
Injecting authoritative project knowledge into the spec prompt is **necessary but not
sufficient** — RUN-011 §3 and the CKG design (line 63) both note the drafter *read*
`schema.prisma` and still invented fields. So the Knowledge Provider's success metric must
be split:
- **Injection (deterministic, unit-testable):** the spec context contains the real field
  sets / module paths. Provable by inspecting the prompt.
- **Adherence (empirical, probabilistic):** the *generated code* uses them. Only measurable
  from generation output, over **N ≥ 5 seeds/feature**, against an **adherence-rate
  threshold** (we proposed 0.9). A single passing re-run can't distinguish a fix from
  sampling luck. Below threshold → escalate (draft self-check / contract-first = CKG's
  Phase-2 Approach C).

*Why it matters to CKG:* the Knowledge Provider could otherwise be declared "done" on an
injection test while the score-vs-reality gap quietly persists at the *content* level —
the same inversion class CKG exists to kill, one layer up.

### D2 — Explicit negatives as a first-class rendered output
Positive field/path tables are not enough to beat the LLM's canonical-name prior. The
recurring inventions (`@/lib/prisma` — 3 recurrences across RUN-008/009/011,
`@/lib/db/<model>` sub-paths, `@/lib/ai/client`) need **explicit negative statements** in
the injected context: *"the Prisma client is `@/lib/db`; there is no `@/lib/prisma`."*
v1 = a **seeded** negative list (cheap, covers the observed recurrences); deriving negatives
from canonical-name priors is a future refinement. CKG can source the *positive* side from
its resolved model; the negative-rendering + seed list is the additive idea.

### D3 — NFR: state omissions, never render an empty authoritative set
When a section is unavailable (no `schema.prisma`, no `tsconfig`), the rendered context must
**state the omission** ("Prisma schema not available — do not assume a field set") and
**omit the field-authority claim** — it must NOT render "use only these fields: (none)",
which falsely authorizes the empty set and is its own hallucination trigger. Implies the
Knowledge Provider's output model carries an explicit `omissions` field, not just absent keys.

### D4 — Refactor-safety gate for the `_collect_upstream_interfaces` seam
The generation-time injection will refactor `prime_contractor._collect_upstream_interfaces`
(today: Mode-A/B inheritance + the heuristic-gated `render_prisma_field_sets`). "Keep the
existing Mode-A/B tests green" is **necessary but not sufficient** — those tests may not
exercise the at-risk branches (absent-anchor warning, Mode-A not-yet-generated producer,
no-TS/JS-upstream early return). Before refactoring, **capture a characterization snapshot**
of the current output on those edge inputs as golden fixtures, then assert byte-for-byte
parity post-refactor. (Also: dropping the `_feature_mirrors_data_model` heuristic gate is
the likely fix for RUN-011 Gap A — PI-001/004/007 plausibly never matched it, so the field
set was never injected.)

---

## Pointers
- Superseded specs (retained, do-not-implement): `APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md`
  (v0.3, CRP R1 applied), `APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md` (v1.1). Their Appendix A/B/C
  hold the full CRP R1 round + dispositions if the CKG track wants the detail behind D1–D4.
- Owning design: `CODE_KNOWLEDGE_GRAPH_DESIGN.md` §8.1 (Knowledge Provider), §as-phased
  (Phase 2 = Knowledge-Provider-driven contract-first).
- Forcing context (shared): `CROSS_FILE_CONTRACT_RESOLUTION.md`, `RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md`.
- The RUN-011 Gap C type-class signature (`prime_postmortem.py`, merged `347b8bd7`) and the
  per-file TS2802 fix are *shipped* and independent of this hand-off.
