# Project-Start Distillation — Outstanding Tasks

**Date:** 2026-07-05
**Status:** The distillation **SHIPPED to `main`** (PR #93, merge `8905140c`) — kernel
(M0–M3) + guided experience (GE-M0–M5) + M5 migration/removal, backward-compatible,
931 SDK + 12 MCP tests green. This doc tracks everything from the session's
requirements/plans that is **NOT complete**. Nothing here blocks the merged work;
these are the honestly-deferred items, spun-out specs, unbuilt viewers, and lifecycle
follow-ups.

Source docs (all on `main`, `docs/design/project-start/`): `PROJECT_START_{REQUIREMENTS
v0.17,PLAN v2.0}`, `GUIDED_EXPERIENCE_{REQUIREMENTS v0.4,PLAN v1.1}`,
`KICKOFF_PANEL_{FACILITATION_DESIGN,GAP_ANALYSIS,OBSERVABILITY_UX_REQUIREMENTS}`,
`MIGRATION_NOTE`.

---

## 1. Deferred requirements — documented-open in the specs, NOT implemented

These are honestly marked deferred/partial in the specs (docs↔code agree). Each is a
real, scoped follow-up if/when the value is wanted.

- **OQ-10 — discovery-offer trigger — ✅ RESOLVED (2026-07-05: ALWAYS OFFER, no
  trigger).** Decision: discovery is **always offered** as a $0, ignorable one-line
  option; there is **no** project-shape gate on whether to offer. It may or may not add
  value on a given project, but it should always be available, and the feature's value
  will grow over time — so gating it now would suppress a maturing capability. This
  **withdraws** the "hard M3 gate" / "solo → silence, multi-stakeholder → offer" trigger
  design: **nothing to build** — the current unconditional offer is the intended state.
  The project-shape / viewpoint-multiplicity / operational-specificity signals survive
  only as *optional prioritization of which personas to suggest* once a human accepts,
  never as a gate. Recorded in `PROJECT_START_REQUIREMENTS.md` (OQ-10 + FR-13 offer
  bullet). *Refs: FR-13, OQ-10.*
- **FR-13a — shaping ranges, never point values — ⏸ DEFERRED (2026-07-05, rationale
  corrected).** Not scheduled for build. Remains an untested HYPOTHESIS (across all eight
  runs no persona ever emitted a shaping range — the behavior it regulates has never
  manifested). **Correction:** an earlier version said "the point-value drafter is deleted
  (NR-7) and no producer of shaping values exists" — **wrong**; Teian (`panel recommend`)
  is a **retained** producer of `estimate`-tier point values (NR-7 reversed). So FR-13a is
  really a deferred **refinement to the kept Teian capability** (should its estimates be
  *ranges*?); the blind-acceptance danger is mitigated by Teian's `estimate` provenance +
  human approve/reject gate, not by the drafter's absence. **Revisit only if** that
  refinement is prioritized OR a ninth run shows a placeable range (then spec the
  width-floor first). Recorded in `PROJECT_START_REQUIREMENTS.md` (FR-13a). *Refs: FR-13a,
  NR-7 (reversed), FR-8.*
- **FR-GE-14 — structural ratification gate — ✅ DONE (2026-07-05, `5169d804`).** The
  gate is now **wired** on the write path. `vipp/apply.py:apply_dispositions` calls
  `assert_ratifiable()` on every claim before `apply_proposal`; the human `confirm()` is
  the ratification (one gate, NR-4), so a synthetic claim reaching the write path
  unratified → `code="unratified"`, no write, left pending (non-synthetic claims pass
  untouched → byte-identical for today's oracle-sourced dispositions, SOTTO). The
  claim-level primitives were moved to the leaf `fde/ratification.py` to avoid the
  `stakeholder_panel↔vipp` import cycle (`stakeholder_panel.provenance` re-exports them,
  API unchanged). Spec: `FR_GE_14_RATIFICATION_WIRING.md`. Tests: 3 new in
  `tests/unit/vipp/test_apply.py` (synthetic+confirm→written; synthetic+no-confirm→
  refused unratified; non-synthetic→unaffected); 310 green across vipp+stakeholder_panel+fde.
  *(Historical note: an earlier version of this entry wrongly called it "prose only" —
  the marker/state/gate primitive were always built + tested; only the consume-path
  wiring was missing, and that is what shipped here.)* *Refs: FR-GE-14, CRP R1-F10.*
- **FR-5a — schema-shape diagnostics.** The `_schema_advisories` port (missing-FK /
  no-PK / island-tables / empty-enum, ~90 LOC in `red_carpet_advisor.py:181-250`) was
  intentionally **skipped** (the FR's "accept the loss and name it" branch). Recorded
  in `MIGRATION_NOTE.md`. Port into kernel `assess` if the diagnostics are wanted.
- **OQ-11 — distillation pass on the discovery implementation — ✅ RESOLVED (2026-07-05:
  DISSOLVED, no distillation owed).** The premise reversed: with discovery **always
  offered** (OQ-10) and Teian `recommend` **retained** (NR-7 reversed — Teian was never
  actually deleted; `panel recommend` is live + CLI-wired), the `stakeholder_panel/`
  module count reflects **essential separation of concerns**, and the anti-principle's own
  metric (*one entry point / one vocabulary / one write path, NOT fewer LOC*) is already
  met. `requirements_panel` is a distinct sibling, not a Teian duplicate. No
  capability-level distillation owed; a thin-module code-hygiene merge is discretionary
  only. *Refs: OQ-11, NR-7 (reversed), OQ-10.*

---

## 2. Owed separate specs — spun out by the distillation

- ~~**VIPP / ground-truth-adjudication capability (parent-plan M6).**~~ **REMOVED
  (CORRECTED 2026-07-05) — this was wrong; nothing is owed here.** VIPP is **fully
  built**: `src/startd8/vipp/` (`evaluate`/`apply`/`ground_truth`/`compose`/`context`/
  `models`), `cli_vipp.py`, `vipp_bridge.py`, `vipp_seam.py`, with specs at
  `docs/design/vipp/` (`VIPP_REQUIREMENTS.md` **v0.3**, reflective→CRP-reviewed) — so the
  claim "own requirements + plan were never written" was false. Greenfield is also
  covered by the sibling **`project init`** capability (`docs/design/project-init/`):
  greenfield/brownfield detection (FR-2) + the greenfield-only `--instantiate`
  ground-truth→proposal mapping, and `vipp negotiate` adjudicates what it honestly can
  (Controlled-Corpus identity-collision; no-ground-truth → labeled ACCEPT routed to the
  panel). The `project-init` spec already litigated and rejected the deeper "originate a
  first inbox from ground truth" idea (FR-5: *"ground truth adjudicates, never
  originates"*). The only *un*-built idea surfaced while re-checking this is **optional
  cross-proposal internal-consistency adjudication** (use a greenfield inbox as its own
  corpus: entity near-miss collisions across authored proposals, dangling `capture`
  refs, duplicate/conflicting entities) — a candidate enhancement, **not** an owed spec;
  pursue only if wanted.
- **Cloud-write trust model (OQ-GE-7).** Cloud is currently **read/preview-only** (typed
  `501 cloud_write_deferred`). Cloud-**write** needs a net-new **auth / tenancy /
  principal / CSRF** design — none exists (`server/auth.py` is a static API-key on POST
  only; the local model refuses cloud by construction). This likely belongs to a broader
  SDK deployment-auth capability, not the guided experience. *Refs: FR-GE-8, OQ-GE-7.*

---

## 3. Unbuilt implementation — requirements written, viewer not built

- **Observability UX viewer** (`KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md` v0.1,
  FR-UX-1..23). The facilitation **transcript contract exists and is written** (by
  `stakeholder_panel/facilitation.py` → `.startd8/kickoff-panel/<session>.json`, per-round
  atomic-replace), but the **viewer was never built**: two-axis expand/collapse (round ×
  role), model/family attribution + cross-family corroboration highlight, the R0 prep
  cards, the halted-session state, live-follow via `--watch`, unratified labeling — as a
  static offline HTML surface (+ optional local served), mirroring the `startd8-consult`
  `store`/`view`/`_webview_template` precedent. Three real transcript fixtures exist to
  build against (the retail #6/#7 + the portal #8 runs).

---

## 4. Lifecycle / follow-up — post-merge

- **Alias-window closure (future deletion PR).** M0/M3 aliases are "one release." The
  M5 **removal criteria** + the **detection-trigger test** (`test_removal_criteria_trigger.py`,
  which flips to *failing* when the aliases are removed) gate a LATER, separate deletion
  PR that removes: the hidden `concierge`/`panel` CLI groups, old CLI subcommand names,
  the MCP `action` alias values, `kickoff-legacy`, and `project init`'s VIPP-default seam.
  Criteria (CRP-corrected): kernel/guided shipped + consumers migrated + grep shows no
  CLI/MCP/documented caller resolves to the retiring code. *Refs: FR-9, FR-12.*
- **Consumer migration (consumer-side actions).** household-o11y + benchmark portal
  should adopt `startd8 project init --with-vipp` before the alias window closes (today
  they get VIPP by default + a deprecation notice = zero break). navig8 is
  kernel-only, zero-impact. *Ref: `MIGRATION_NOTE.md`.*
- **Live cost verification (FR-13c H3).** Cost aggregation + budget hard-halt are wired,
  but tested `$0`/mocked. Confirm real per-round/session `cost_usd` surfaces + the budget
  cap fires in a paid live facilitation run.
- **Anti-re-accretion CI completeness (FR-GE-7 / CRP R2-F7).** The "exactly one
  kickoff-domain group" + metaphor-name-scan tests were added; verify the scan covers
  the **error / `--verbose` / traceback** surfaces fully (not just help output), and that
  the MCP action-enum vocabulary is enumerated (R3-F5).

---

## 5. Research / validation — optional

- **Panel discovery on a genuinely under-specified project.** All facilitation
  experiments ran on the retail demo + benchmark portal, both fairly well-specced. The
  case the whole "beat the blank canvas" pitch rests on — *does the panel discover
  something when the human genuinely hasn't thought it through?* — was never tested. This
  is the fair counter-experiment to the "mirror when cold / lens when facilitated"
  findings.

---

## 6. Housekeeping

- **Retire the session worktrees + branch:** `~/Documents/dev/startd8-guided-wt`
  (branch `docs/project-start-distillation`), `~/Documents/dev/startd8-kickoff-impl`
  (branch `feat/kickoff-kernel`, now merged), and this `startd8-tasks-wt`. **Mind the
  gitignored-payload hazard** — run `git -C <wt> status --ignored` / `du -sh <wt>/.startd8`
  BEFORE `git worktree remove` (it silently deletes gitignored stores).
- **`mcp` package** was installed into the SDK `.venv` while closing the merge
  verification gap — a legitimate dependency for MCP work; left in place.
- **Junk files** `errc.txt` / `outc.txt` in the `startd8-kickoff-impl` worktree root
  (subagent stderr redirects) — safe to delete.
- **Mark the shipped specs "IMPLEMENTED"** — `PROJECT_START_REQUIREMENTS` v0.17,
  `GUIDED_EXPERIENCE_REQUIREMENTS` v0.4, and both plans now describe merged code (PR #93);
  a status stamp would prevent future readers treating them as pending design.

---

## References
- **Merged:** PR #93 → `main` merge `8905140c` (kernel + guided experience + migration).
- **Design docs:** `docs/design/project-start/` on `main`.
- **Session trail (memory):** `project_project_start_distillation.md`.
