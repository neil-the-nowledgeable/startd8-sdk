# CRP Focus — Kickoff Persona Experiences

**Target (least-reviewed):** `PERSONA_EXPERIENCES_REQUIREMENTS.md` (v0.3) + `PERSONA_EXPERIENCES_PLAN.md` (v1.0)
**Both docs are brand-new** — no prior review rounds. Dual-document mode.

## Settled — do NOT relitigate

These were decided with the user or established by the planning pass. Reviewers should build on them,
not reopen them:

- **Persona is a lens over the ONE canonical experience** — not three parallel experiences, not a
  prose fork. (NR-1.)
- **Orthogonal to `posture`** (fluency axis ⟂ trust axis); no 3×2 matrix of experiences. (NR-3.)
- **Selection = explicit, project-remembered, changeable** — via the `guided` preference ladder
  (NOT posture, which the planning pass proved has no store). (FR-1.)
- **Scope = persona may pick different DEFAULTS**, reconciled to byte-identity: fills **unledgered**
  fields only, never overrides an explicit choice; same explicit decisions ⇒ byte-identical output;
  provenance-tagged. (FR-4/5/6.)
- **Default persona = Intermediate = today's walk, byte-identical.** (FR-2.)
- **Two-knob model** (DISCLOSURE × SURFACE); Beginner = expanded+reduced, Advanced = compact+full.
- **Naming SETTLED = `audience`** (both code AND user-facing CLI verb), resolving the
  `stakeholder_panel` "persona" ×319 overload (§0.1/§0.3, OQ-12). `persona` is reserved for the
  roster concept. **Do not relitigate the word**; the filename/title keep "Persona" as a cosmetic
  follow-up. Reviewers MAY verify terminology is applied *consistently*, but not reopen the choice.

## Where independent review is most valuable

- **FR-9 (disclosure without forking)** — the single NR-1 risk. Is the "same-doc delimiter-marked
  region" model actually sufficient, or does plain-language beginner prose diverge enough in
  structure that a projection can't hold? Is there a cleaner single-source mechanism?
- **FR-11 pre-pass (`apply_audience_defaults`)** — writing shielded defaults *before* a filtered walk.
  Any ordering/idempotency hazard vs. the existing confirm machinery? Interaction with OQ-10
  (persona-switch re-run).
- **OQ-8** — ledger provenance encoding (new `mode` value vs. additive `provenance` field) and
  backward-tolerance for existing `v1` ledgers on disk.
- **OQ-9** — which fields Beginner shields (domain- vs field-granular); the safety of silently
  writing them.
- **Byte-identity guarantee (FR-4)** — is a golden test sufficient, or does persona leak into output
  through any path the planning pass missed (e.g. ordering, timestamps, `at` fields in the ledger)?

## Known-thin areas (author-acknowledged)

- Web persona control scope (OQ-11) is deliberately deferred to M5.
- No persona **inference** in v1 (NR-2) — explicit only.
