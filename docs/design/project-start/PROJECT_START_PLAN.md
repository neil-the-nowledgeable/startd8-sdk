# Project-Start Distillation — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-04
**Tracks:** `PROJECT_START_REQUIREMENTS.md` v0.2
**Posture:** Phased, additive-first, nothing deleted until the kernel ships and
consumers migrate (NR-5, FR-9/FR-12).

---

## Guiding constraints (from the planning pass)

1. **The `kickoff` name is taken.** `kickoff_app` (the metaphor group) holds it
   (`cli.py:1256`). The kernel rename is *blocked* until that group is
   renamed/retired. This orders M1 after the metaphor group is demoted.
2. **Three greenfield verbs, not four.** `derive` is brownfield (`core.py:352`);
   greenfield schema comes from `generate contract --promote` (`cli_generate.py:734`).
3. **Un-bundling is code, not docs**, in exactly two places: `assess`'s
   unconditional panel injection (`core.py:256,267`) and `project init`'s always-on
   VIPP posting (`project/init.py:138,142`).
4. **Absorb the command map, reject the playbook.** ~40-60 LOC, not ~650.

---

## Milestones

### M0 — Reconcile the surface inventory (doc + spike; no behavior change)
- Inventory all four onboarding surfaces: `concierge`, `kickoff` (metaphor),
  `project init`, and the MCP tool. Diff the greenfield instantiate path of
  `project init` (`project/init.py:121-156`) against `instantiate-kickoff`
  (`writes.build_instantiate_plan`) to answer OQ-8: same package or divergent?
- **Exit:** FR-1a disposition decided (fold vs. scope-out); OQ-5 answered by
  reading `~/Documents/dev/navig8/` for its actual consumption.
- **Satisfies:** corrected FR-1 scope, OQ-5, OQ-8.

### M1 — Rename the kernel group to the plain verbs
- Demote the metaphor group: rename `kickoff_app` → a deprecated name
  (e.g. `kickoff-legacy`) under a deprecation notice (`cli.py:1256`, `cli_kickoff.py`).
- Rename `concierge_app` `name="concierge"` → `"kickoff"` (`cli_concierge.py:24`);
  rename subcommands `instantiate-kickoff`→`instantiate`, `derive-contract`→`derive`.
- Keep old action strings as hidden aliases in `handle_concierge_tool`
  (`core.py:313-366`) and old CLI subcommand names as hidden aliases for one
  release (MCP `ConciergeInput.action` enum + scripts depend on them).
- **Satisfies:** FR-1, FR-9, FR-10. **Blocked-by:** M1's metaphor-group demotion.

### M2 — `assess` emits the next command
- Port `_blocker_command` + command constants (`red_carpet_advisor.py:63-73,348-358`)
  into `concierge/core.py`; attach `next_command` to each blocker in
  `_assess_cascade` (`core.py:298-310`) and a headline `next_command` on
  `build_assess` (`core.py:175`). Update CLI render (`cli_concierge.py:135`) + MCP
  docstring.
- **Optional (FR-5a):** port `_schema_advisories` (`red_carpet_advisor.py:181-250`,
  ~90 LOC) for FK/PK/island/enum diagnostics, or record the loss in the migration note.
- **Satisfies:** FR-5 (+ FR-5a optional). **Rejects:** the ranked playbook.

### M3 — Cut the Panel edge from the kernel
- Remove the unconditional `stakeholders` injection + `_assess_stakeholder_roster`
  from `build_assess` (`core.py:256,260-277`), or gate it behind an opt-in flag
  mirroring `vipp_opted_in`. Update `red_carpet_advisor.py:314-343` consumers and
  any test asserting the `stakeholders` key.
- **Verify** SOTTO byte-identical-when-absent for the kernel path (FR-15).
- **Satisfies:** FR-13, FR-15 (panel half).

### M4 — De-couple VIPP from `project init`
- Make the VIPP posting opt-in in `establish_postings` (`project/init.py:129,138-142`);
  add `--with-vipp` for brownfield. Default path must not `import vipp`.
- Confirm the seam stays no-op (`vipp_seam.py:250-256`).
- **Satisfies:** FR-14, FR-15 (VIPP half).

### M5 — Deprecation, migration, removal criteria (no deletions)
- Deprecation notices on the metaphor surfaces (Welcome Mat `serve.py`/`web.py`,
  Red Carpet `cli_kickoff.py:335,485,567`), each pointing to the `kickoff` verb
  that replaces it.
- Write the **navig8 migration note** (FR-11): what it consumed, the verb it now
  uses, and whether FR-5a diagnostics were load-bearing for it.
- Codify **removal criteria** (FR-12): kernel verbs shipped + consumer(s) migrated
  + no external caller in the deterministic-provider entry points ⇒ eligible for
  a later, separate deletion PR.
- **Satisfies:** FR-9, FR-10, FR-11, FR-12, NR-5.

### M6 (separate specs, not this doc) — Un-bundled capabilities
- Stakeholder Panel → its own "content review" requirements (must reconcile with
  the CLAUDE.md bucket rule).
- VIPP → its own "brownfield migration / auto-adjudication" requirements
  (paired with `derive`).

---

## FR → Milestone traceability

| FR | Milestone |
|----|-----------|
| FR-1, FR-9, FR-10 | M1 |
| FR-1a | M0 (decide) → M4 (execute if fold) |
| FR-2, FR-3, FR-4, FR-7, FR-8 | already implemented; M1 renames + M2 MCP nit |
| FR-5, FR-5a | M2 |
| FR-11, FR-12 | M5 |
| FR-13, FR-15 (panel) | M3 |
| FR-14, FR-15 (VIPP) | M4 |
| NR-5 | all (no deletion) |

---

*Plan v1.0 — sequenced so the kernel becomes the documented surface (M1-M2)
before any COMPENSATORY layer is cut (M3-M4) and before anything is deleted (M5,
deferred).*
