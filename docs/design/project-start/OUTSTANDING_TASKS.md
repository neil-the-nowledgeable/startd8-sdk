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

- **OQ-10 — the conditional-offer trigger for discovery (the big one).** The spec calls
  this a *hard M3 gate*, but the Deepen phase is currently offered **unconditionally**
  (a pointer whenever `--deepen`/a session exists). The "solo → silence,
  multi-stakeholder → offer" project-shape gate does not exist. **Design input from the
  experiments:** trigger on **domain viewpoint-multiplicity, NOT team size**, and favor
  **operationally-specific personas** (the ones with a causal relationship to the
  strategy). Guided routing (`guided_routing.py`) keys only on greenfield-vs-brownfield
  (FR-GE-3), not this signal. *Refs: FR-13, OQ-10.*
- **FR-13a — shaping ranges, never point values.** Self-flagged HYPOTHESIS; the
  roster-discovery value is unproven. No `shaping-range` provenance (FR-8) and no
  width-floor/degenerate-range check exist. NR-7's point-value prohibition is enforced
  only by *deletion* of the Teian drafter, not by the data-layer width-floor. **Do:**
  either prove roster-discovery value (run `panel ask-all` for a real "surface a
  viewpoint you'd have missed" data point) or shrink the claim to capability-discovery
  and implement the width-floor only if kept. *Refs: FR-13a, FR-8, NR-7.*
- **FR-GE-14 — structural ratification gate.** Synthetic facilitation output is marked
  "unratified" in **prose only**; there is no machine-checkable provenance/ratification
  field and no kernel refuse-until-ratified gate. **Mitigated in practice** (transcripts
  are never written into the kickoff input YAMLs, so they never reach the kernel
  consume path), so this is low-risk — implement only if a structural guarantee is
  wanted. *Refs: FR-GE-14, CRP R1-F10.*
- **FR-5a — schema-shape diagnostics.** The `_schema_advisories` port (missing-FK /
  no-PK / island-tables / empty-enum, ~90 LOC in `red_carpet_advisor.py:181-250`) was
  intentionally **skipped** (the FR's "accept the loss and name it" branch). Recorded
  in `MIGRATION_NOTE.md`. Port into kernel `assess` if the diagnostics are wanted.
- **OQ-11 — distillation pass on the discovery implementation.** GE-M2 detangled the
  *concierge/conductor* modules, but the `stakeholder_panel/` discovery machinery
  (~20 modules) was **not** distilled — "keeping the purpose did not bless the module
  count." A focused reduction pass is owed (only the Teian drafter was removed).

---

## 2. Owed separate specs — spun out by the distillation

- **VIPP / ground-truth-adjudication capability (parent-plan M6).** `project init` was
  scoped OUT of the kernel and re-filed as this capability's setup entrypoint (OQ-8),
  but the capability's **own requirements + plan were never written**. It is the
  "adjudicate proposals against existing ground-truth once a schema exists" feature,
  paired with `derive`. *Refs: FR-1a, FR-14, parent-plan M6.*
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
