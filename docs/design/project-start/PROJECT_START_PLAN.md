# Project-Start Distillation — Implementation Plan

**Version:** 2.0 (Rewritten to reqs v0.17 — kernel + consolidation; guided experience delegated)
**Date:** 2026-07-04
**Tracks:** `PROJECT_START_REQUIREMENTS.md` v0.17 (+ CRP R1–R3 triage applied).
**Companion plan:** `GUIDED_EXPERIENCE_PLAN.md` (the optional guided-experience build).
**Posture:** Phased, additive-first; **retirement → CONSOLIDATION** (v0.17 — Welcome
Mat / Red Carpet are consolidated into the guided experience, not deleted; only the
Teian point-value ghost is dropped). Nothing deleted until the kernel ships and
consumers migrate (NR-5, FR-9/FR-12).

> **v2.0 rewrite.** Catches the plan up to reqs v0.17 + the CRP triage. Changes vs
> v1.2: the essential model is now a spectrum (kernel + *optional* guided experience,
> §0.4); OQ-8 resolved → `project init` **scope-out**; OQ-9 resolved → `derive`
> **stays on-surface**; retirement → **consolidation**; the panel facilitation +
> FR-13c hardening moved to the **guided-experience plan**; CRP fixes folded (FR-12
> gate scope, FR-10 MCP-alias, FR-1a alias-window). This plan now owns the **kernel**
> + cross-cutting (scope-out, consolidation-delegation, removal); the guided layer is
> in the companion plan.

---

## Guiding constraints

1. **The `kickoff` name is taken.** `kickoff_app` (the metaphor group) holds it
   (`cli.py:1260`). The kernel rename is *blocked* until that group is demoted —
   orders M0a (demote) before M0b (rename).
2. **Three greenfield verbs + a brownfield on-ramp.** `derive` is brownfield
   (`core.py:352`) and **stays on the `kickoff` surface** (OQ-9); greenfield schema
   comes from `generate contract --promote` (`cli_generate.py:734`).
3. **The two kernel edges are code, not docs.** (a) `assess`'s unconditional panel
   injection (`core.py:256,267`, + `PANEL_CONSUMABLE`) → kernel-own the coverage
   core, discovery opt-in-loaded (M2). (b) `project init`'s always-on VIPP posting
   (`project/init.py:138,142`) → **scope-out** to the VIPP capability, VIPP opt-in
   (M3, OQ-8).
4. **Absorb the command map, reject the playbook.** ~40-60 LOC, not ~650 (M1).
5. **The guided experience is a companion, not this plan.** The panel facilitation +
   FR-13c hardening + the Welcome-Mat/Red-Carpet consolidation live in
   `GUIDED_EXPERIENCE_PLAN.md`; this plan delegates to it (M4).
6. **CRP-fixed removal gate.** Removal criteria check **CLI subcommands + MCP
   `action` enum values + documented consumers** resolve to zero — NOT the
   `deterministic-provider` entry-point group (which passes vacuously; R1-F1/R2-F1).

---

## Milestones

### M0 — Kernel surface: rename to `startd8 kickoff` (three verbs + on-ramp)
- **M0a (demote first).** Rename `kickoff_app` (metaphor group) → `kickoff-legacy`
  under a deprecation notice (`cli.py:1260`, `cli_kickoff.py`), freeing the `kickoff`
  name. **Must precede M0b** (R1-S2: the name must be free before the kernel claims
  it; dry-run verifies `kickoff` unregistered — acyclic).
- **M0b (rename kernel).** `concierge_app` `name="concierge"` → `"kickoff"`
  (`cli_concierge.py:24`); subcommands `instantiate-kickoff`→`instantiate`,
  `derive-contract`→`derive`. `derive` stays on-surface as the labeled brownfield
  on-ramp (OQ-9); `assess`/`survey` surface `kickoff derive` only when `survey`
  detected existing models (`core.py:120`).
- **Alias window (R1-F2 fix).** Hidden aliases for one release covering **both** the
  old CLI subcommand names **and** the MCP `ConciergeInput.action` enum values
  (`core.py:313-366`; scripts/MCP key on `action` strings).
- **Satisfies:** FR-1, FR-9, FR-10, OQ-9.

### M1 — `assess` emits the next command
- Port `_blocker_command` + constants (`red_carpet_advisor.py:63-73,348-358`) into
  `concierge/core.py`; attach `next_command` to each blocker (`core.py:298-310`) +
  a headline on `build_assess` (`core.py:175`). Update CLI render + MCP docstring.
- **Optional (FR-5a):** port `_schema_advisories` (~90 LOC) or record the loss.
- **Satisfies:** FR-5 (+ FR-5a optional). **Rejects:** the ranked playbook.

### M2 — Kernel-owned coverage; cut the panel-in-assess edge
- **Kernel-own the coverage core.** Move the "which inputs count" domain list into
  the kernel so `build_assess` reports unfilled fields **without importing
  `stakeholder_panel`** and **removes `PANEL_CONSUMABLE`** from kernel `core.py`
  (`core.py:38-41,256,267,274`; R1-F4). Specify the import-error semantics: absence
  ⇒ byte-identical, not a silently-degrading try/except (R2-F2). The $0 essential
  act: *identify* what needs populating.
- **Drop Teian.** Remove the point-value drafter (`panel recommend`/`Recommendation`),
  keeping its $0 coverage signal as the discovery trigger (NR-7); enforce
  shaping-ranges-not-point-values (FR-13a, `shaping-range` provenance).
- **Discovery/facilitation itself → the guided experience (M4 / companion plan).**
- **Satisfies:** FR-13 (coverage half), FR-13a, FR-15 (panel half), NR-3, NR-7.

### M3 — `project init` scope-out (OQ-8)
- Re-file `project init` as the **setup entrypoint of the un-bundled VIPP /
  ground-truth-adjudication capability** (FR-1a/FR-14). Make the VIPP posting
  **opt-in** (`establish_postings`, `project/init.py:138-142`); default kernel path
  must not `import vipp`.
- **Consumer-safe alias window (R1-F7/FR-1a):** the *old* `project init` invocation
  keeps posting VIPP **by default until the alias window closes**, so household-o11y
  + benchmark portal do not double-break (scope-out + opt-in-flip at once).
- **Satisfies:** FR-1a, FR-14, FR-15 (VIPP half).

### M4 — Consolidation → the guided experience (delegated)
- Welcome Mat + Red Carpet + the panel are **consolidated** into one optional guided
  experience (v0.17 retirement→consolidation) — **built per `GUIDED_EXPERIENCE_PLAN.md`**
  (its M0–M5: routing, single entry point, concierge/conductor detangle, facilitation
  promotion+hardening, surface parity, cloud-read). Only the Teian ghost is deleted.
- **Satisfies:** parent FR-9 (as consolidation), the guided-experience FR-GE-* set.

### M5 — Migration + removal criteria (no deletions)
- Deprecation notices on the consolidated-away surfaces, each pointing to the
  `kickoff` guided verb that replaces it.
- Write the **navig8 migration note** (FR-11): navig8 = kernel-only (`instantiate` +
  `derive`), zero impact (OQ-5 resolved).
- Codify **removal criteria** (FR-12, CRP-fixed): kernel/guided shipped + consumers
  migrated + **no CLI subcommand / MCP `action` value / documented consumer resolves
  to the retiring code** (grep-verified; NOT the deterministic-provider group) ⇒
  eligible for a later deletion PR. Add a **detection trigger** (R2-F1) so the gate's
  satisfaction is noticed, not passive.
- **Satisfies:** FR-9, FR-10, FR-11, FR-12, NR-5.

### M6 (separate spec) — Un-bundled VIPP capability
- VIPP → its own "ground-truth proposal adjudication / brownfield" requirements,
  paired with `derive` and with `project init` as its setup entrypoint (from M3).

---

## FR → Milestone traceability

| FR | Milestone |
|----|-----------|
| FR-1, FR-9, FR-10, OQ-9 | M0 |
| FR-2, FR-3, FR-4, FR-7, FR-8 | already implemented; M0 renames + M1 MCP nit |
| FR-5, FR-5a | M1 |
| FR-13 (coverage), FR-13a, FR-15 (panel), NR-3, NR-7 | M2 |
| FR-1a, FR-14, FR-15 (VIPP), OQ-8 | M3 |
| FR-13b, FR-13c, FR-6/NR-2 guided layer, FR-GE-* | M4 → `GUIDED_EXPERIENCE_PLAN.md` |
| FR-11, FR-12 | M5 |
| VIPP capability | M6 (separate spec) |
| NR-5 | all (no deletion) |

---

*Plan v2.0 — rewritten to reqs v0.17 + CRP triage. Sequenced so the kernel becomes
the documented surface (M0–M2) before `project init` scope-out (M3), before the
guided-experience consolidation (M4 → companion plan), and before any deletion (M5,
deferred; retirement→consolidation means only the Teian ghost is deleted). The
guided-experience build is `GUIDED_EXPERIENCE_PLAN.md`. No longer stale.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Bump version + add milestones for FR-13b/13c/OQ resolutions | R1 | Applied (partial): version banner bumped to v1.2 with a KNOWN-STALE warning; the milestone additions themselves are the **full plan rewrite to reqs v0.16 — tracked next work item**, not applied in this triage pass. | 2026-07-04 |
| R1-S2 | Fix circular M1 "blocked by itself" | R1 | Applied inline — M1 now states acyclic intra-milestone ordering (demote `kickoff_app` before renaming `concierge`; M1a→M1b option; dry-run name-free check). | 2026-07-04 |
| R1-S3 | Make MCP read-only structural (concrete M-task + test) | R1 | Accepted — reqs FR-7 now carries the structural MCP-floor acceptance test (this pass); the plan M-task/exit lands in the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R1-S4 | Correct M5 removal-criteria scope | R1 | Accepted — reqs FR-12 scope corrected (R1-F1, applied); M5's task text update rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R1-S5 | Add per-milestone acceptance/exit criteria + SOTTO byte-identity tests | R1 | Accepted — belongs in the **full plan rewrite (tracked next item)**; the FR-15 byte-identity tests are now specified reqs-side. | 2026-07-04 |
| R1-S6 | Sequence-guard the consumer double-break (alias window) | R1 | Accepted — reqs FR-1a now states the alias-window condition (R1-F7, applied); the M4 sequence-guard task rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R1-S7 | Schedule + gate the OQ-11 distillation debt | R1 | Accepted — needs an M-slot or dated deferral; **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R1-S8 | State PANEL_CONSUMABLE disposition in M3 | R1 | Accepted — reqs FR-15 now names the PANEL_CONSUMABLE disposition (R1-F4, applied); M3 task wording rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S1 | Make M0's "fold" branch concrete or remove it | R2 | Accepted — code evidence favors scope-out-only (reqs FR-1a/OQ-8 RESOLVED); collapse M0 to a single disposition in the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S2 | Bind a plan task to KICKOFF_PANEL_FACILITATION_DESIGN.md (FR-13b) | R2 | Accepted — new FR-13b milestone gating against the design doc; **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S3 | M2 gate: FR-5a decision recorded before M5 migration note | R2 | Accepted — add the M2-exit forcing function; **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S4 | Add activation gate to M5 removal-criteria | R2 | Accepted — reqs FR-12 now requires a detection trigger (R2-F1, applied); the plan-side activation mechanism rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S5 | Verify safe-write chokepoint intact after M1–M3 renames | R2 | Accepted — reqs FR-7 now requires confinement tests to survive the renames (R2-F3, applied); the M1/M3 exit check rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S6 | Resolve OQ-10 in a plan milestone, not just CRP | R2 | Accepted — reqs OQ-10 now a hard M3-exit gate (R2-F5, applied); the M3 codification task rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R2-S7 | Closing-note version mismatch (v1.0 vs header v1.1) | R2 | Applied inline — closing note updated to v1.2 to match the header. | 2026-07-04 |
| R3-S1 | M2: re-target ported command map (drops CMD_RED_CARPET_AGENT) + M1↔M2 ordering | R3 | Accepted — M2 must re-target the retiring-surface command + a command-drift test + post-M1 name resolution; **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R3-S2 | M1 name-REUSE: kernel `kickoff` must forward old metaphor subcommands | R3 | Accepted — add M1 forwarding task ("moved to `kickoff-legacy`") so repurposed-name callers get guidance not a bare Typer error; **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R3-S3 | M3 `assess` output-schema break (removed `stakeholders` block) needs a migration owner | R3 | Accepted — reqs FR-15 now names this as a scheduled plan-side migration item (this pass); the M3 consumer-survey + deprecation-marker task rides the **full plan rewrite (tracked next item)**. | 2026-07-04 |
| R3-S4 | Re-scope M0: its exits are already RESOLVED/SETTLED | R3 | Accepted — M0 must become a verification (not re-decide) milestone or be marked satisfied-by-reqs-v0.16; **full plan rewrite (tracked next item)**. | 2026-07-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | No plan-side suggestion was rejected; all S-items are correct. The bulk are ACCEPTED-but-deferred-to-the-full-rewrite (recorded in Appendix A with that resolution), not applied inline, because they require re-milestoning the stale plan against reqs v0.16 rather than a local edit. | 2026-07-04 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-04

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-04 00:00:00 UTC
- **Scope**: Plan-side (S-prefix) review + requirements↔plan staleness, weighted per the focus file toward FR-9..12 retirement soundness, import-edge surgery, FR-13c orchestrator hardening, and consumer-migration risk. Independent reviewer. Appendix A/B/C were empty → this is R1. **Headline finding: the plan (v1.1, self-labeled "Tracks reqs v0.4") is materially stale against requirements now at v0.11+/§0.15 — FR-13b, FR-13c, OQ-10/11/12, NR-6, and the entire facilitation/mixed-model/multi-round + orchestrator-hardening body have no milestone.**

**Executive summary (top risks / gaps):**
- The plan tracks reqs **v0.4**; requirements are at **v0.11+** with FR-13b/FR-13c and OQ-10/11/12 added. No milestone covers the facilitation structure or the H1/H2/H3 orchestrator hardening.
- **FR-13c has zero plan coverage** — artifact-grounding fidelity, assumptions-as-gate, and cost tracking are unscheduled despite being "required before the panel is more than a prototype."
- **M1 has a circular blocker** ("Blocked-by: M1's metaphor-group demotion") — the milestone is blocked by itself.
- **FR-12 removal criterion is mis-scoped** (deterministic-provider entry points ≠ the retiring CLI/MCP surfaces).
- **The MCP structural-read-only fix (FR-7/D9) is demoted to a parenthetical "M2 MCP nit"** with no task/exit criterion.
- **Consumer double-break risk** (FR-1a scope-out + FR-14 opt-in flip land in different milestones M0/M4 with no ordering guard for the 2 VIPP apps).
- **No test/validation strategy** anywhere in the plan — every milestone lists edits, none lists an acceptance check.
- **OQ-11 distillation debt** (slim the ~20-module discovery package) is marked "owed" in M3/M6 but never scheduled or gated.

**First-pass suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | critical | Bump the plan's version banner and add milestones for the requirements added since v0.4: FR-13b (facilitation structure), FR-13c (orchestrator hardening H1/H2/H3), and the OQ-10/11/12 resolutions. The banner "Version 1.1 … Tracks reqs v0.4" is stale against reqs v0.11+/§0.15. | The plan silently omits the largest body of new requirements (all the panel facilitation + hardening work); an implementer following the plan would ship the reclassified-but-unhardened prototype. | Header block ("Version:", "Tracks:") + Milestones list | Every FR/NR/OQ with a `RESOLVED`/`required` status in reqs appears in the FR→Milestone table. |
| R1-S2 | Risks | high | Fix the circular blocker in M1: "**Blocked-by:** M1's metaphor-group demotion." A milestone cannot block itself. State the true ordering: the `concierge`→`kickoff` rename step is blocked by the `kickoff_app` demotion step *within* M1 (intra-milestone ordering), or split them into M1a (demote metaphor group) → M1b (rename kernel). | The name-collision (FR-1) is the plan's #1 sequencing hazard; a self-referential blocker line leaves the ordering ambiguous and could produce a rename that collides with the still-registered `kickoff_app`. | M1, "**Satisfies:** FR-1, FR-9, FR-10. **Blocked-by:** M1's metaphor-group demotion." | The plan states an acyclic ordering; a dry-run rename verifies `kickoff` is free before `concierge` claims it. |
| R1-S3 | Security | high | Add a concrete M-task (fold into M1 or M2) to make MCP read-only **structural** per FR-7/D9: route the MCP path through `handle_concierge_read` (not `handle_concierge_tool`, `startd8_mcp.py:3200`), with an acceptance test. Today it appears only as the parenthetical "M2 MCP nit" in the FR-traceability table. | FR-7 elevates this from incidental (write branches happen to return previews) to structural; a parenthetical is not a schedulable task and will be dropped. | FR→Milestone table row "FR-2, FR-3, FR-4, FR-7, FR-8 … M2 MCP nit"; add explicit M-step | Test: an MCP `action` on a write verb cannot reach a write branch even if preview return is removed (structural gate, not preview-incidental). |
| R1-S4 | Ops | high | Correct M5's removal-criteria task to match FR-F1: replace "no external caller in the deterministic-provider entry points" with a check across CLI subcommands, MCP `action` enum, and documented consumers. | M5 inherits FR-12's mis-scoped gate verbatim; deletion could proceed while a live CLI/MCP caller exists. | M5, "Codify **removal criteria** (FR-12) … no external caller in the deterministic-provider entry points" | Removal PR shows zero references to retiring modules across all three registries. |
| R1-S5 | Validation | high | Add a per-milestone acceptance/exit criterion and a byte-identical-when-absent test strategy. Only M0 has an explicit "Exit:"; M1–M5 list edits with no verification. The two SOTTO invariants (FR-15: VIPP seam + panel-absent assess) especially need named tests. | The requirements are heavy on testable invariants (byte-identical assess, structural read-only, alias dispatch); a plan with no validation column cannot prove them and invites silent regressions. | Each milestone M1–M5; add an "Exit/Validation:" line mirroring M0 | Each milestone names ≥1 automated check; FR-15's two seams each have a byte-identity test. |
| R1-S6 | Interfaces | high | Sequence-guard the consumer double-break: FR-1a scope-out (decided M0, executed later) and FR-14 VIPP-opt-in (M4) must not both take effect for the household-o11y/portal invocation path in the same release without an alias window that keeps `project init` posting VIPP by default. | §0.3 shows those 2 apps reach VIPP through `project init`'s always-on posting; M0 and M4 landing independently can break both the name and the default at once, contradicting FR-1a "consumer break = zero." | M4 ("De-couple VIPP from `project init`") + FR→Milestone row for FR-1a | Migration test: pre-change `project init` command still yields a VIPP posting until the alias window closes. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Architecture | medium | Schedule and gate the OQ-11 distillation debt. M3 says "**Owed:** a distillation pass on the ~20-module discovery implementation" and M6 repeats it, but neither assigns it a milestone or a removal-criterion. Give it an M-slot or explicitly defer it with a tracking issue. | The anti-principle lens is the doc's spine; keeping ~20 modules for a "1-novel-gap-per-14-calls" capability (OQ-12) without a distillation gate re-imports the accidental complexity the whole effort removes. | M3 "**Owed:**" bullet and M6 second bullet | The plan either has a distillation milestone with a module-count target, or a dated deferral note referencing OQ-11. |
| R1-S8 | Data | medium | M3's "kernel-own the coverage core" step must also state the disposition of `PANEL_CONSUMABLE` (`core.py:267,274`), not only the domain-list move — otherwise the residual ship-state coupling flagged in §0 survives and FR-15's byte-identity invariant is unprovable. | The plan mirrors FR-15's gap (see R1-F4): moving `core.py:38-41` alone leaves `PANEL_CONSUMABLE` coupling `assess` to the panel's presence. | M3, first bullet "Kernel-own the coverage core" | Post-M3, `PANEL_CONSUMABLE` no longer referenced in kernel `core.py`; assess byte-identical with panel absent. |

**Endorsements / Disagreements:** none — Appendix A/B/C were empty at R1 (no prior untriaged items to react to). The requirements-side items R1-F1, R1-F2, R1-F4, R1-F7 above are the paired counterparts to plan items R1-S4, R1-S3-adjacent, R1-S8, R1-S6 respectively; triage should route them together.

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-04

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-04 18:30:00 UTC
- **Scope**: Plan-side (S-prefix) R2 review. R1 (claude-opus-4-8) covered version staleness, circular blocker, MCP task, removal-criterion scope, missing validation, consumer double-break, OQ-11 scheduling, and PANEL_CONSUMABLE disposition. This pass brings a different lens: the decision-routing gaps, facilitation-spec binding, internal milestone logic, and the OQ-10 resolution ownership vacuum. Appendix A/B empty; R1 is the only prior round (all R1 items untriaged).

**Executive summary (top risks / gaps):**

- **M0's "fold" branch is a ghost exit path.** M0 decides fold-vs-scope-out for FR-1a, but if "fold" is chosen, no milestone has the ~7-site VIPP stripping work. The plan only maps "M4 (execute if fold)" to the VIPP opt-in, not to the full fold of `project init` into the kernel. A fold-disposition at M0 leaves implementers with no plan.
- **No plan task binds to `KICKOFF_PANEL_FACILITATION_DESIGN.md`.** Requirements v0.11 names it as the spec for FR-13b; the plan has no step to create, validate, or gate against it.
- **OQ-10 trigger decision has no plan home.** The requirements say "Decide during CRP" — but no milestone accepts that decision and no exit criterion verifies it.
- **FR-5a decision has no deadline before M5 depends on it.** The migration note (M5/FR-11) requires knowing whether schema-shape diagnostics were ported or dropped, but the "port or record loss" choice is only loosely pinned to M2 with no forcing function.
- **M5's codified removal criteria have no activation gate.** FR-12 says deletion is "a later, separate change" — but nothing in the plan triggers a review when the criteria are met.
- **The safe-write chokepoint (FR-7) has no plan step.** The confinement + dir-fd-relative writes clause in FR-7 must survive the M1–M3 refactors; no milestone verifies the chokepoint is intact after renames.

**First-pass suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Architecture | high | Make M0's "fold" exit path concrete or explicitly remove it. The FR→Milestone table shows "FR-1a: M0 (decide) → M4 (execute if fold)" but no milestone contains the ~7-site VIPP-stripping work a fold requires; `project init`'s VIPP coupling is at posting, inbox scaffold, seq, gitignore, negotiate/apply, status (`project/init.py:138-408`). Either add an M4a task that outlines the fold work, or state that M0 may only exit with "scope-out" (which the code evidence already favors). | If M0 exits "fold," implementers have no plan and will improvise the most complex task in the milestone set. | FR→Milestone row "FR-1a: M0 (decide) → M4 (execute if fold)"; M4 task list | M0 exit criterion names exactly one disposition (scope-out), or M4 lists the specific files/sites for a fold path. |
| R2-S2 | Architecture | high | Add a plan task (in a milestone for FR-13b coverage) to bind to and validate against `KICKOFF_PANEL_FACILITATION_DESIGN.md`. Requirements v0.11 cites it as the implementation spec for the facilitation scaffold (shared-context block, means-ends templates, cross-role round, synthesis, mixed-model assignment), but no plan milestone creates or gates against it. | Without a plan step that treats `KICKOFF_PANEL_FACILITATION_DESIGN.md` as a gate artifact, the spec is a free-floating reference that implementers may or may not consult; FR-13b's first-class facilitation structure will be re-improvised from experiment prose. | A new milestone covering FR-13b (absent from the plan as noted in R1 coverage matrix), or an explicit task under M3 | The milestone exit criterion names the design doc and verifies the shipped orchestrator satisfies its requirements. |
| R2-S3 | Risks | medium | Add an M2 gate: the FR-5a decision (port schema-shape diagnostics or record loss) must be made and recorded *before* M5's migration note is drafted. Currently "Optional (FR-5a): port or record loss" is pinned to M2 with no forcing function; M5 ("write the navig8 migration note") depends on that decision being settled. | If M5 is reached without the FR-5a decision logged, the migration note will be written with an open question or a wrong assumption about what navig8 retains. The optional framing hides a sequencing dependency. | M2 "Optional (FR-5a)" bullet; M5 migration-note task | M2 exit criterion includes "FR-5a disposition recorded (port or explicit loss)"; M5 migration note references that disposition. |
| R2-S4 | Ops | medium | Add an activation gate to M5's removal-criteria codification. FR-12 says eligible code is "deleted in a later, separate PR" but M5 only codifies the criteria; nothing in the plan triggers a deletion review when criteria are met. Name a check mechanism: a dated review issue, a CI staleness check on the deprecated modules, or a CLAUDE.md watchlist entry. | A removal-criteria list with no activation gate is a "delete when you feel like it" policy; the anti-principle lens the doc applies means accidental-complexity residue stays in the tree indefinitely without a trigger. | M5, "Codify **removal criteria** (FR-12)" bullet | Removal criteria include ≥1 named activation mechanism (e.g. "a dated review comment on the deletion PR template, or a CI check that fails if the deprecated modules exceed N months past the criteria date"). |
| R2-S5 | Validation | medium | Add a plan step verifying the safe-write chokepoint (FR-7's root-confinement + atomic dir-fd-relative writes) is intact after M1–M3 renames. The M1 rename moves module paths and the M3 refactor touches `core.py` write paths; neither has an exit check confirming the chokepoint survived. | The confinement invariant is a security property that must hold across refactors; a rename that moves the chokepoint without an integrity check creates a silent regression window. | M1 exit/validation line (or M3), cross-referencing FR-7 | Named test: a write via the MCP (or a monkey-patched CLI path) to a path outside the root directory is rejected at the chokepoint even after all renames are complete. |
| R2-S6 | Interfaces | medium | Resolve OQ-10 in a plan milestone, not just in CRP. The requirements say "Decide during CRP" for the discovery-offer trigger signals (authored roster ≥ N distinct roles, operational-specificity heuristic, etc.), but no milestone accepts that decision and no exit criterion verifies it. If OQ-10 is settled in CRP, the outcome must land in a plan step. | M3 ("Make discovery an opt-in-loaded offer… `survey`/`assess` compute cheap project-shape signals") depends on the OQ-10 signal set being decided; without a plan step, M3 can ship with placeholder logic and the trigger is effectively undefined. | M3 task list; OQ-10 note in FR→Milestone table | M3 exit criterion includes "OQ-10 signal set codified in a testable spec or comment"; a deterministic test covers at least two trigger cases (offer / no-offer). |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S7 | Risks | low | The plan's closing note ("*Plan v1.0 — sequenced so the kernel becomes the documented surface before any COMPENSATORY layer is cut*") is version-labeled v1.0 but the header says v1.1. The version mismatch is a minor but real source of ambiguity for downstream readers and tools that parse version strings. | A version label inconsistency is exactly the "accidental complexity accretes silently" pattern the doc's own anti-principle warns against — small, ignored, and eventually load-bearing when another tool relies on the wrong version. | Closing note line "*Plan v1.0 — sequenced…*" | Closing note version matches the header "Version: 1.1". |

**Endorsements (untriaged R1 items this reviewer agrees with):**

- **R1-S1** (bump plan version + add milestones for FR-13b/c): strongly endorse — the staleness is the root cause of the largest cluster of plan gaps.
- **R1-S2** (fix circular M1 blocker): strongly endorse — a self-referential blocker is an acyclic-ordering violation and will produce a rename collision.
- **R1-S5** (add per-milestone acceptance criteria): strongly endorse — the plan's validation gap is pervasive; M0 is the only milestone with an explicit "Exit:" line.
- **R1-S8** (PANEL_CONSUMABLE disposition in M3): endorse — moving the domain list without addressing the flag leaves the ship-state coupling intact.

---

#### Review Round R3 — claude-fable-5 — 2026-07-04

- **Reviewer**: claude-fable-5
- **Date**: 2026-07-04 21:30:00 UTC
- **Scope**: Plan-side (S-prefix) R3. R1 covered version staleness, the circular M1 blocker, the MCP task, removal-criterion scope, missing validation, the consumer double-break, OQ-11 scheduling, and PANEL_CONSUMABLE; R2 covered the fold ghost path, facilitation-spec binding, the FR-5a deadline, the removal activation gate, chokepoint integrity, and OQ-10's plan home. **Third lens: contract stability of what the milestones themselves ship — the payloads M1/M2/M3 move (command strings, output schemas, name bindings) change meaning in transit, and M0's exits are already settled.** All claims verified against source (`red_carpet_advisor.py:61-73,348-358`, `core.py:256`, focus-file SETTLED list).

**Executive summary:**
- **M2's ported command map points at the surfaces M5 retires.** The constants block being ported verbatim includes `CMD_RED_CARPET_AGENT = "startd8 kickoff red-carpet --agent"`, and `_blocker_command` returns it for app/manifest/form/flow gaps — a faithful ~40-60 LOC port makes the *kernel's* `assess` emit a deprecated Red Carpet command as its "exact next command."
- **M1 is a name REUSE, not a removal** — after the swap, old metaphor `startd8 kickoff …` invocations resolve to the kernel group with different semantics; no alias window covers a *repurposed* name.
- **M3's byte-identical target is anchored to a counterfactual build** — today's `assess` always emits a `stakeholders` domain (`core.py:256`), so M3 is a visible output-schema change for all three live consumers, untreated as a migration item anywhere.
- **M0's two exit criteria are already RESOLVED** in reqs v0.15 (OQ-5 §0.3, OQ-8→FR-1a) and SETTLED in the CRP focus file — as written, M0 instructs implementers to re-open settled decisions.

**First-pass suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Interfaces | high | M2 ("Port `_blocker_command` + command constants (`red_carpet_advisor.py:63-73,348-358`)") must add a re-targeting step: the constants include `CMD_RED_CARPET_AGENT = "startd8 kickoff red-carpet --agent"` and `_blocker_command` returns it for app/manifest/form/flow sections — a verbatim port makes kernel `assess` emit a command M5 deprecates. Also state the M1↔M2 ordering for the emitted verb names (`concierge …` vs `kickoff …`): if M2 lands first, every emitted `next_command` goes stale at M1's rename. | FR-5's whole point is "emits the exact next command"; emitting a retiring-surface command (or a pre-rename name) as the exact next step is worse than emitting none — it actively routes new users onto the deprecated path during the transition window. | M2 first bullet; add an explicit ordering note vs M1 | A command-drift test (the advisor module already anticipates one: "No bare `startd8 …` literal should live outside this module") asserting no kernel-emitted `next_command` references a surface carrying an FR-10 deprecation notice, and all emitted names resolve in the post-M1 CLI registry. |
| R3-S2 | Risks | high | M1's swap ("rename `kickoff_app` → … `kickoff-legacy`" then give `kickoff` to the kernel) is a name REUSE: old metaphor invocations (`startd8 kickoff red-carpet --agent` — still emitted by unported advisor output and doc-referenced by the benchmark portal per §0.3) will resolve to the *kernel* group and fail with an unknown-subcommand error carrying no forwarding guidance. Add an M1 task: the new kernel `kickoff` group must recognize the old metaphor subcommand names (`red-carpet`, `wizard`, …) for the alias window and answer "moved to `kickoff-legacy`" with the replacement kernel verb. | FR-10's deprecation notices live on the OLD surfaces — but a repurposed name means old callers never *reach* the old surface to see the notice. This is the one transition case a deprecation-notice strategy structurally cannot cover, and it lands exactly at the plan's #1 sequencing hazard (the name collision). | M1 task list, after the `concierge`→`kickoff` rename bullet | Test: invoking each pre-M1 metaphor subcommand against the post-M1 CLI exits with a message naming `kickoff-legacy` + the replacing kernel verb (not a bare Typer "No such command" error). |
| R3-S3 | Interfaces | high | M3's exit ("Byte-identical `assess` when discovery is not accepted (FR-15)") is measured against a build that never knew the panel existed — but that is NOT today's output: `assess` currently always emits `out["domains"]["stakeholders"]` (`core.py:256`). Meeting FR-15 therefore *removes a top-level domain block* from every existing consumer's `assess` output. Add to M3: (a) a consumer survey of the three §0.3 apps (+ MCP callers) for `stakeholders`-block consumption; (b) a stated output-schema deprecation treatment (e.g. one release emitting the block with a `deprecated: true` marker, or an explicit "no consumer parses it" finding recorded in the FR-11 note). | The plan treats M3 as pure de-coupling, but the SOTTO invariant's baseline flip makes it a breaking output change in disguise; FR-11's migration note covers retiring *surfaces*, not the kernel's own output shape, so this break has no owner in any milestone. | M3, "Make discovery an opt-in-loaded offer" bullet; cross-ref M5/FR-11 | A recorded before/after `assess` JSON diff for each live consumer plus either a nil-consumption finding or a one-release deprecation marker on the removed block. |
| R3-S4 | Architecture | medium | Re-scope M0: both of its exit criteria are already settled — "FR-1a disposition decided (fold vs. scope-out)" was RESOLVED → scope-out (reqs FR-1a/OQ-8, and the CRP focus file lists OQ-8 as SETTLED/do-not-relitigate), and "OQ-5 answered by reading `~/Documents/dev/navig8/`" was RESOLVED in §0.3 (migration impact = zero). Rewrite M0 as a *verification* milestone (re-confirm the recorded diffs/evidence against current code, record it) or mark it satisfied-by-reqs-v0.15 — do not leave a first milestone that instructs implementers to re-open decisions the focus file forbids relitigating. | A plan whose M0 re-decides settled questions invites exactly the churn the SETTLED list exists to prevent, and it burns the first milestone on work the requirements doc already contains with evidence. Complements (does not duplicate) R1-S1's version-staleness finding and R2-S1's fold-ghost finding: even the *decided* branch is still phrased as undecided. | M0 heading + "**Exit:**" line | M0's exit line names verification of recorded resolutions (with a dated evidence note), not a fresh decision; no M0 task re-opens an OQ marked RESOLVED in reqs ≥v0.15. |

**Endorsements (untriaged prior items this reviewer agrees with):**

- **R1-S1** (plan version bump + milestones for FR-13b/c): strongly endorse — still the root cause; my R3-S1/S3/S4 are all downstream symptoms of the plan freezing at reqs v0.4.
- **R1-S5** (per-milestone acceptance criteria): strongly endorse — three of my four findings would have surfaced at plan-time had M1-M3 carried exit checks.
- **R1-S6 / R1-F7 pairing** (consumer double-break sequence guard): endorse — and note R3-S3 adds a third break axis (assess output shape) to the same consumer set, so the migration guard should cover all three.
- **R2-S1** (fold branch is a ghost): endorse — R3-S4 is its complement: the decide-step is stale on one side, the execute-step empty on the other.
- **R2-S6** (OQ-10 needs a plan home): endorse — M3's trigger logic is unimplementable without it.

**Disagreements:** none.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirements-doc FR/NR/OQ to the plan milestone(s) that address it and rates coverage. Rated against reqs v0.11+/§0.15; the plan self-labels v0.4, so post-v0.4 requirements score Partial/Gap by construction.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (single surface, 3 greenfield verbs) | M1 | Full | — |
| FR-1a (`project init` scope-out) | M0 (decide) → M4 | Partial | No alias-window guard for the 2 VIPP apps' invocation path (R1-S6/R1-F7); "consumer break = zero" unproven in the plan. |
| FR-2 (`survey`) | already implemented; M1 rename | Full | — |
| FR-3 (`derive` brownfield) | already implemented; M1 rename | Partial | OQ-9 refinement (`next_command: kickoff derive` only when models detected) not scheduled. |
| FR-4 (`instantiate`) | already implemented; M1 rename | Full | — |
| FR-5 (`assess` emits next command) | M2 | Full | — |
| FR-5a (schema-shape diagnostics) | M2 (optional) | Partial | "port or record loss" decision has no exit criterion; navig8-dependency check deferred to M5 note. |
| FR-6 / NR-2 (handoff not host; no conductor) | (implicit) | Gap | Directly contradicts FR-13b/FR-13c facilitation orchestrator; plan does not reconcile (R1-F3). |
| FR-7 (safe-write floor + structural MCP read-only) | "M2 MCP nit" (parenthetical) | Partial | Structural-read-only fix is a parenthetical, not a scheduled task (R1-S3). |
| FR-8 (provenance discipline) | already implemented | Partial | No provenance value for FR-13a shaping ranges (R1-F5). |
| FR-9 (nothing deleted until kernel lands) | M1, M5 | Full | — |
| FR-10 (deprecation markers) | M1, M5 | Partial | Alias window not required for MCP `action` enum (R1-F2). |
| FR-11 (navig8 migration note) | M5 | Full | — |
| FR-12 (removal criteria) | M5 | Partial | Criterion cites wrong entry-point group (R1-S4/R1-F1). |
| FR-13 (conditionally-offered discovery) | M3 | Partial | Trigger signals (OQ-10) not turned into concrete plan tasks; single-domain external-validity caveat (R1-F9) absent. |
| FR-13a (shaping ranges not point values) | M3 | Partial | Enforcement mechanism/provenance not specified in the plan (R1-F5). |
| FR-13b (facilitation STRUCTURE + mixed-model) | (none) | Missing | No milestone for the shared-context block, means-ends templates, cross-role round, synthesis, or mixed-model assignment — the "real capability" per §4. |
| FR-13c (orchestrator hardening H1/H2/H3) | (none) | Missing | Artifact-grounding fidelity, assumptions-as-gate, cost tracking all unscheduled despite "required before more than a prototype" (R1-S1). |
| FR-14 (VIPP opt-in) | M4 | Full | — |
| FR-15 (per-seam SOTTO invariant) | M3 (panel), M4 (VIPP) | Partial | `PANEL_CONSUMABLE` disposition unaddressed (R1-S8/R1-F4); no byte-identity test named (R1-S5). |
| NR-1..NR-6 | (implicit / NR-5 = "all") | Partial | NR-6 (not re-authoring the $0 cascade) not asserted anywhere in the plan. |
| NR-7 (Teian dropped) | M3 | Full | — |
| OQ-10 (discovery-offer trigger) | (referenced in M3) | Partial | Signals enumerated in reqs but not converted to a deterministic $0 detection task. |
| OQ-11 (discovery distillation debt) | M3/M6 "Owed" | Partial | Owed but unscheduled/ungated (R1-S7). |
| OQ-12 (prove discovery E2E) | (none) | Missing | Resolved empirically in reqs §4; no plan step captures the resulting scoping (low-yield, operationally-specific personas, facilitated-not-cold). |

---

## Requirements Coverage Matrix — R2

Analysis only (R2 lens). Focuses on items the R1 matrix rated Partial/Gap where the R2 review found additional dimensions not captured by R1's gap notes.

| Requirement | Plan Step(s) | Coverage | R2 Additional Gap Notes |
| ---- | ---- | ---- | ---- |
| FR-1a (`project init` scope-out) | M0 (decide) → M4 | Partial | M4 "execute if fold" branch has no actual task content — fold path is a ghost (R2-S1). Scope-out is the only path with a concrete plan. |
| FR-5a (schema-shape diagnostics) | M2 (optional) | Partial | Decision has no deadline gate before M5 depends on it (R2-S3). Optional framing hides a sequencing dependency. |
| FR-7 (safe-write floor) | "M2 MCP nit" (parenthetical) | Partial | Chokepoint integrity across M1–M3 renames is unverified (R2-S5). Confinement invariant could silently regress. |
| FR-12 (removal criteria) | M5 | Partial | Criteria have no activation gate; "later, separate PR" is a policy without a trigger (R2-S4). Also mis-scoped (R1-S4). |
| FR-13 (conditionally-offered discovery) | M3 | Partial | OQ-10 trigger signal set has no plan step to receive and codify the CRP decision; M3 can ship with undefined trigger logic (R2-S6). |
| FR-13b (facilitation STRUCTURE) | (none) | Missing | `KICKOFF_PANEL_FACILITATION_DESIGN.md` named as spec in reqs v0.11 but not referenced in any plan task; facilitation structure will be re-improvised without a gate artifact (R2-S2). |
| FR-13c (orchestrator hardening H1/H2/H3) | (none) | Missing | No milestone (confirmed from R1); R2 adds: synthesizer-vs-raw-round disagreement protocol (R1-F6 addresses persistence but not conflict) not required anywhere. |
| NR-6 (not re-authoring $0 cascade) | (implicit) | Gap | Neither R1 nor plan asserts this invariant; a plan step should name it as a negative constraint so scope-creep is visible. |
| OQ-10 (discovery-offer trigger) | (referenced in M3) | Partial | "Decide during CRP" disposition needs a plan milestone to receive and implement the decision; no current home (R2-S6). |

---

## Requirements Coverage Matrix — R3

Analysis only (R3 lens: payload/contract stability + evidence traceability). Adds dimensions not captured in the R1/R2 matrices; ratings unchanged where R1/R2 already recorded the gap.

| Requirement | Plan Step(s) | Coverage | R3 Additional Gap Notes |
| ---- | ---- | ---- | ---- |
| FR-1 (single surface, rename) | M1 | Partial (downgraded from R1's Full) | The name-REUSE hazard: post-swap, old metaphor `kickoff` invocations hit the kernel group with no forwarding guidance — a case FR-10's on-surface deprecation notices structurally cannot cover (R3-S2). |
| FR-1a / OQ-5 / OQ-8 | M0 | Partial | M0's exits are already RESOLVED in reqs v0.15 and SETTLED in the focus file; M0 as written re-opens them (R3-S4). |
| FR-5 (`assess` emits next command) | M2 | Partial (downgraded from R1's Full) | Ported constants include a retiring-surface command (`CMD_RED_CARPET_AGENT`); M1↔M2 ordering of emitted verb names unstated; no command-drift check (R3-S1). |
| FR-11 (migration note) | M5 | Partial (downgraded from R1's Full) | Covers retiring surfaces only; the M3 `assess` output-schema change (removed always-present `stakeholders` block) has no migration owner (R3-S3). |
| FR-13 / §0.2 model | M3 | Partial | Plan implements FR-13's trigger bullets, but §0.2's cold field-triggered chain and FR-13b's facilitated process are two different products (reqs-side R3-F1); M3 cannot be implemented coherently until the requirements pick one. |
| FR-13a (shaping ranges) | M3 ("enforce shaping-ranges") | Gap (new dimension) | The capability M3 would enforce is empirically untested — no run ever produced a range (reqs R3-F2); enforcement without an exercised behavior is unverifiable. |
| FR-13b(5) (mixed-model) | (none) | Missing | Beyond R1/R2's no-milestone finding: no degraded-mode contract when <2 model families are available — single-family runs can masquerade as de-correlated convergence (reqs R3-F5). |
| FR-13c H3 (cost) | (none) | Missing | The referenced "budget gate" is defined nowhere; SDK `startd8.costs` should be the substrate; offer/acceptance discloses no cost estimate (reqs R3-F6). |
| FR-7 (safe-write floor) | "M2 MCP nit" | Partial | New write path outside the floor: panel transcript persistence (`run_kickoff_panel.py:365`, direct `Path` write) — becomes normative if R1-F6 is accepted without R3-F4. |
| Doc-as-state integrity | (n/a) | Gap | Reqs header v0.15 vs changelog ending at v0.11 (reqs R3-F3) compounds the plan's "Tracks v0.4" staleness: neither document's version trail currently supports the diff-by-version workflow R1 used. |
