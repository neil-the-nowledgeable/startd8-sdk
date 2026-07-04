# Guided Experience — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-04
**Tracks:** `GUIDED_EXPERIENCE_REQUIREMENTS.md` v0.2
**Posture:** Detangle + consolidate + promote; deterministic-first; nothing forced; kernel byte-identical when absent.

---

## Guiding constraints (from the planning pass)

1. **No SDK deployment-mode self-awareness exists** — route on explicit preference >
   surface > project-shape; never *detect* agent-presence (D1).
2. **The conductor is deterministic-first** — the $0 advisor + wizard already guide;
   LLM is strictly opt-in (D5). "Guided" costs $0.
3. **The facilitation process is an un-packaged script** — promote before harden;
   route its writes through the safe-write floor (D2/D8).
4. **The win is surface/vocab/write-path reduction, not LOC** (D3/D7).
5. **Cloud is read-only for now** — cloud-write has no trust substrate (D6).

---

## Milestones

### M0 — Routing seam (small, safe)
- Add a `guided` preference reusing the `concierge_agent.py:59-75` precedence ladder
  (`--guided/--no-guided` → project `build-preferences.yaml` → global
  `~/.startd8/config.json` → default-quiet). Route on: explicit > served-surface >
  `build_assess` project-shape. **No agent-presence detection.**
- One ignorable offer line; `--no-guided` ⇒ kernel byte-identical (FR-GE-1/2/3).
- **Satisfies:** FR-GE-1, FR-GE-2, FR-GE-3, FR-GE-4.

### M1 — Single entry point + vocabulary retirement
- Introduce `startd8 kickoff guided` (or no-subcommand ⇒ guided offer) sequencing
  Orient→Guide→Deepen over `orchestrator.py:build_kickoff_plan`.
- Retire `concierge_app`/`panel_app` as top-level groups (`cli.py:1259-1260`); alias
  their verbs under `kickoff` (hidden aliases for one release — parent FR-10).
- **Net:** 3 groups → 1, 23 verbs → ~12.
- **Satisfies:** FR-GE-5, FR-GE-7, OQ-GE-2.

### M2 — Concierge/conductor detangle (the real reduction)
- Merge the concierge-UI quartet (`concierge_agent`/`_apply`/`_view`/`tui_concierge`)
  → one view+apply (the parity view-model `concierge_view.py` becomes THE view).
- Merge `red_carpet_completion` + `wizard` + `orchestrator` (three overlapping
  "what's next" projections over the same advisor output) → one conductor module.
- Collapse `chat.py`'s three constructors (`new_kickoff_chat`/`new_agentic_kickoff_chat`/
  `new_red_carpet_chat`) → one parametrized constructor.
- Verify all writes ride `concierge/safe_write.py` (FR-GE-13).
- **Target:** 24 → ~16 modules. **Satisfies:** FR-GE-6, FR-GE-7, FR-GE-13, OQ-GE-3/6.

### M3 — Promote & harden facilitation (biggest lift)
- **Promote** `run_kickoff_panel.py` orchestration → `stakeholder_panel/facilitation.py`,
  built over the existing `StakeholderPanel`/roster/guards (OQ-GE-8 sizes the
  abstraction). Route transcript persistence through the safe-write floor (fixes D8).
- Then harden: **H1** artifact-grounding fidelity (read the running app / `survey`,
  not just schema); **H2** assumptions-as-gate (halt on ≥N high-impact/low-confidence);
  **H3** cost tracking (panel already tracks `cost_usd` — wire it end-to-end).
- **FR-GE-11** raw-round persistence; **FR-GE-12** anti-smoothing as a *test* (assert
  named raw-round tensions survive the synthesis; `_SYNTH_SYS` already instructs it —
  make it verifiable).
- **Satisfies:** FR-GE-10, FR-GE-11, FR-GE-11a, FR-GE-12, FR-GE-13.

### M4 — Surface parity (CLI / TUI / served)
- One view-model (`concierge_view.py` is already the parity oracle) feeds CLI, TUI,
  and the local served UI. Cross-surface parity test.
- **Satisfies:** FR-GE-9.

### M5 — Cloud scoping (read-only)
- Ship cloud as **read/preview-only** (Orient + Deepen-view); local write uses the
  existing loopback+token model. Human downloads produced inputs, writes locally.
- Cloud-**write** deferred (OQ-GE-7 — net-new auth/tenancy).
- **Satisfies:** FR-GE-8 (standalone + cloud-read), NR (no cloud-write yet).

---

## FR → Milestone traceability

| FR | Milestone |
|----|-----------|
| FR-GE-1/2/3/4 | M0 |
| FR-GE-5, FR-GE-7 | M1 (+ M2 detangle) |
| FR-GE-6, FR-GE-13 | M2 |
| FR-GE-10/11/11a/12 | M3 |
| FR-GE-9 | M4 |
| FR-GE-8 | M5 |
| FR-GE-14 | all (human ratifies; never authors/decides) |

---

*Plan v1.0 — sequenced so routing (M0) and the single entry point (M1) land before
the detangle (M2), the facilitation promotion+hardening (M3) is isolated as the big
lift, and cloud stays read-only (M5) until the OQ-GE-7 auth design exists.*

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
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R3 — claude-fable-5 — 2026-07-04

- **Reviewer**: claude-fable-5
- **Date**: 2026-07-04 21:05:00 UTC
- **Scope**: Third-pass plan review (S-prefix). R1 covered milestone coupling, the M3 split, routing edges, write audits, cloud spend, version drift; R2 covered operationalization and the M5→M3 hidden dependency. R3 lens: cross-document consistency (parent v0.17 as amended, KICKOFF_PANEL_* siblings), verifiability of the consolidation numbers (all re-verified on disk: 24 modules, 438 LOC script, 23 verbs across the 3 groups at `cli.py:1258-1260`), and interfaces no milestone owns. Focus-ask deltas live in the requirements-file R3 block; plan-relevant deltas: Ask 1 → R3-S2/S3/S4, Ask 2 → R3-S1, Ask 3 → R3-S5.

##### Executive summary

- M3 re-routes transcript persistence with no acceptance criterion that the sibling observability-UX doc's transcript contract (path, schema, **round-by-round write cadence** for live-follow) survives the re-route — a cross-doc interface neither doc owns.
- M1 cites parent FR-10 for the alias window but aliases only CLI verbs; parent FR-10 *as amended by the parent's own CRP* (parent Appendix A, R1-F2) requires the window to also cover the MCP `ConciergeInput.action` enum — the `startd8_concierge` MCP tool is a live retired-vocabulary surface the plan never touches.
- The two headline numbers ("23 → ~12 verbs", "24 → ~16 modules") have no enumerated baseline or disposition mapping, so neither gate is checkable at M1/M2 exit.
- M2's module-count done-criterion quietly re-imports the metric the requirements v0.3 explicitly retired (FR-GE-7: the win is surfaces/vocab/write-paths, NOT counts) — a reqs↔plan framing contradiction.
- M0's "reuse the ladder verbatim" inherits a falsy-fall-through defect: the cited ladder skips unusable/falsy layers, so an explicit `guided: false` at a higher layer would fall through — breaking FR-GE-4 exactly where the plan claims to satisfy it.
- After M2 merges `tui_concierge` away, M4's "TUI" parity leg has no named surface to test.

##### Numbered suggestions (S-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-S1 | Interfaces | high | Add an M3 acceptance criterion: safe-write re-routing **preserves the transcript contract** consumed by `KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md` — path (`.startd8/kickoff-panel/<session_id>.json`, FR-UX-1), §6 schema, and **per-round incremental writes** (FR-UX-17 live-follow polls the file as rounds land). If the floor's atomicity is end-of-session, live-follow dies while every current M3 bullet still passes; require per-round atomic-replace (or version the contract and update the UX doc in the same milestone). | The UX viewer is a shipped-spec consumer of the exact artifact M3 relocates behind the floor; no milestone owns this interface. Sharper, concrete instance of the cross-milestone-dependency class R2-S4 raised for M5. | M3, after "Route transcript persistence through the safe-write floor" | Test: run promoted facilitation; assert the transcript exists at the contract path mid-run and gains rounds incrementally; UX-doc FR-UX-3/FR-UX-17 fixtures pass against floor-written output. |
| R3-S2 | Interfaces | high | M1 must include the **MCP surface** in vocabulary retirement: parent FR-10 (cited by M1) was amended to require hidden aliases for BOTH CLI names AND the MCP `ConciergeInput.action` enum for the one-release window. Add an M1 bullet covering the `startd8_concierge` action vocabulary (alias + deprecation warning), or explicitly scope MCP out with rationale. | M1 claims "Satisfies: FR-GE-5, FR-GE-7" but retires only the CLI vocabulary; the MCP tool keeps the old metaphor vocabulary alive user-facing, and the parent already codified this exact lesson (parent Appendix A, R1-F2). | M1, after the "Retire `concierge_app`/`panel_app`" bullet | Test: MCP actions carry aliases + deprecation warnings for one release; the five retired names absent from MCP tool/action names+descriptions at the alias-window close. |
| R3-S3 | Validation | medium | Make the consolidation numbers checkable: publish a **verb-disposition table** (each of the verified 23 verbs → kept / renamed-under-kickoff / hidden-alias / retired) as an M1 exit artifact, and define the module-count measurement scope for M2's "24 → ~16" (`kickoff_experience/` only? does M3's +1 `facilitation.py` in `stakeholder_panel/` count against it?). | "~12" and "~16" are currently underivable from anything in either doc; without an enumerated baseline the M1/M2 exit gates are vibes. The 23/24 baselines verify today — pin them before the detangle moves the ground. | M1 "**Net:**" line + M2 "**Target:**" line | CI/gate: `--help` verb census equals the disposition table; module census over the declared scope equals the target ±0. |
| R3-S4 | Architecture | medium | Reconcile the metric framing: FR-GE-7 (v0.3) explicitly retired "net-reduce modules" as the headline, yet M2's done-criterion is a module count (and R1-S1 proposes making it THE gate). Label "24 → ~16" an **internal tracking signal subordinate** to the one-entry-point/one-vocabulary/one-write-path metric, with the surface/vocab/write-path checks as the actual M2 exit gate. | The plan re-imports the metric the requirements reframed away; if M2 lands at 18 modules with a perfect surface/vocab/write-path outcome, the plan as written reads as failure — inverting the requirement's honest-metric decision. | M2 "**Target:**" line; footnote to the R1-S1 coupling if accepted | Doc consistency check: the M2 exit gate enumerates surface/vocab/write-path assertions; module count reported but not gating. |
| R3-S5 | Data | medium | M0: replace "reusing the `concierge_agent.py:59-75` precedence ladder" with "reusing the precedence **pattern**", and specify (a) **tri-state semantics** — the existing ladder resolves non-empty strings and *skips falsy layers*, so naive reuse makes explicit `guided: false` at project level fall through to a global `guided: true`, violating FR-GE-4; (b) the concrete file path (code says `docs/kickoff/inputs/build-preferences.yaml`, plan says "project `build-preferences.yaml`") and key name. | M0 is "small, safe" only if the reused shape actually fits: the agent-spec ladder has no meaningful "explicitly off" value; the guided preference is exactly that. Plan-side twin of requirements R3-F2; distinct from R2-S7 (drift coupling) — this is a day-one semantic mismatch, not future drift. | M0, first bullet | Contract test: project `guided: false` + global `guided: true` ⇒ no offer; `--no-guided` beats any config true. |
| R3-S6 | Ops | low | M4 names CLI/TUI/served parity, but M2 merges `tui_concierge` into the one view+apply — after M2, which TUI surface remains for M4 to test? Name it (main-TUI mixin? new kickoff screen?) or drop the TUI leg from M4 with rationale. | A parity milestone against an unnamed surface can't be planned or tested; as sequenced, the only named TUI module is gone before M4 starts. | M4 milestone | M4 exit: the parity test enumerates its three concrete surfaces by module/entry point, all extant post-M2. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-S4: the M5→M3 hidden dependency is real; R3-S1 is a second, already-live instance of the same class (transcript contract), strengthening the case for a cross-milestone interface note.
- R2-S2: the chat-constructor parameter surface must be named or the collapse is cosmetic.
- R1-S6: the CI write-audit is the only durable "one write path" enforcement; R3-S1's contract test should ride the same gate.
- R1-S10: FR-GE-14 needs an owning milestone; M3 (transcripts) + M2 (conductor outputs) is the right split.

**Disagreements** (untriaged prior items this reviewer would qualify):
- R1-S1 (partial): the M1↔M2 coupling is right, but making "24 → ~16 modules" the M2 done-criterion conflicts with FR-GE-7's reframed metric — couple the milestones, gate on surface/vocab/write-path, and demote the module count to a tracking signal (R3-S4).

---

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-04

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-04 18:30:00 UTC
- **Scope**: Second-pass architectural review; weighted per focus file on consolidation soundness, FR-GE-11a promotion, routing edges, safe-write coverage, cloud read-only, and plan↔requirements gaps. Lens: what R1 (strong, broad coverage) missed — second-order effects, operationalization gaps, and cross-cutting concerns.

##### Executive summary

- M3's H3 cost-tracking task says "wire it end-to-end" without defining the surface/scope of that wiring — a vague acceptance criterion on the highest-risk milestone.
- M2's chat-constructor collapse is described in terms of *count* (three → one parametrized) but the parameter surface is completely unspecified; a badly shaped parametrization reproduces the structural sprawl inside a single constructor.
- M3's H1 grounding ("read the running app / `survey`, not just schema") has no acceptance test; "artifact-grounding fidelity" is asserted but not operationalized.
- FR-GE-6 ("no new engine") has no CI-enforceable criterion in the plan — R1-S6 covers write-path audit but the no-new-engine invariant is a separate concern.
- The plan's `Tracks: v0.2` line is stale (requirements are v0.3), caught by R1-S9 but worth a plan-side note on version pinning going forward.
- M5 is positioned last but contains a decision (LLM-invoking vs static-only Deepen on cloud) that may gate M3 scope — the sequencing hides a cross-milestone dependency.
- No milestone owns the "Deepen is skippable mid-flow" guarantee; a user who opts in to Deepen but abandons early needs a clean exit path that leaves Guide outputs intact.

##### Numbered suggestions (S-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Validation | high | M3 H3 ("wire cost_usd end-to-end") must define what "end-to-end" means: at minimum, name the scope — per-round cost, session total, where it is surfaced (CLI output, transcript header, budget gate), and what "budget-gated" means for the facilitation invoke. "Already tracks cost_usd — wire it" is not a testable acceptance criterion. | H3 is a hardening requirement under the riskiest milestone; leaving "end-to-end" undefined means the wiring can be any no-op partial connection that technically satisfies the text. | M3 milestone, H3 bullet | Test: a facilitation run with a configured budget cap is refused when the cap is exceeded; the per-session spend appears in the session transcript or CLI output. |
| R2-S2 | Architecture | high | M2's chat-constructor collapse ("three constructors → one parametrized") must name the parameter surface (at minimum: what varies — agent-presence, surface type, script mode — and what the parametrization contract is). A badly shaped omnibus constructor internalizes the structural sprawl rather than removing it. | Three constructors exist for a reason; collapsing to one without specifying the parameter space risks producing a constructor with N=3 boolean flags that is functionally three constructors under a single name. | M2 milestone, 'Collapse chat.py's three constructors' bullet | Test: the parametrized constructor has a documented, bounded parameter set; a call-site analysis shows no flag combination is dead code. |
| R2-S3 | Validation | medium | M3 H1 ("read the running app / `survey`, not just schema") needs an operationalized acceptance criterion: what specifically constitutes "grounded on the real system" vs "schema-only," and what does the facilitation module do if the running app is unavailable (fallback vs hard fail)? | "Artifact-grounding fidelity" is the most abstract of the three hardening requirements, yet it gates the quality of every facilitation output; without a criterion, any implementation that reads a file satisfies it. | M3 milestone, H1 bullet | Test: facilitation with the live app unavailable either (a) hard-fails with a clear message, or (b) degrades to schema-only with an explicit warning surfaced to the human; grounded mode uses a live `survey` artifact distinct from the schema. |
| R2-S4 | Ops | medium | Add an explicit cross-milestone dependency note: M5's decision on "LLM-invoking vs static-transcript-only Deepen on cloud" (raised by R1-S8) can scope-affect M3 (if cloud Deepen must be static-only, M3 must design a transcript-serving path). Sequencing M5 after M3 may embed the wrong assumption into M3's implementation. | M5 is positioned last as "cloud scoping," but if the outcome is "cloud Deepen = static transcripts only," M3 must build transcript persistence in a cloud-readable form from the start. A post-M3 M5 discovery of this constraint forces M3 rework. | M5 milestone preamble; add a note: 'If Deepen is static-transcript-only on cloud, the cloud-readable transcript format must be decided before M3 lands' | Traceability: M3 exit gate requires a documented decision on cloud-Deepen mode; M5 does not retroactively redefine M3 artifacts. |
| R2-S5 | Interfaces | medium | Add a "Deepen skip / early-exit" acceptance criterion to M3: a user who opts into Deepen but abandons before completion must exit cleanly with Guide outputs intact and no partial transcript committed to the safe-write store. | FR-GE-5 marks Deepen as optional but no milestone ensures mid-Deepen abandonment is handled; partial transcript commits or Guide-output corruption on Deepen exit would silently violate FR-GE-1 (kernel byte-identical when guided not completed). | M3 milestone, new acceptance criterion | Test: a Deepen session interrupted mid-round leaves Guide-produced inputs unchanged and the safe-write store either clean or atomically rolled back. |
| R2-S6 | Architecture | medium | M2 needs a "no new engine" audit criterion (parallel to the write-path audit in R1-S6): an explicit check that the merged conductor module introduces no new extractor, generator, writer, or readiness computation (FR-GE-6). The detangle is the primary risk window for accidental engine introduction. | Merging 3 modules into 1 is the highest LOC-manipulation moment; it is the most likely place for a developer to "just add" a utility that becomes a second readiness engine. | M2 milestone, after 'Merge red_carpet_completion + wizard + orchestrator' bullet | CI check: assert no new entry-points or class definitions matching extractor/generator/writer/readiness-compute patterns appear in the merged conductor relative to the baseline. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S7 | Risks | medium | The routing-ladder "reuse verbatim" from `concierge_agent.py:59-75` creates a hidden coupling: if that source module changes its ladder logic, guided-experience routing changes silently. M0 should extract the ladder into a shared utility or pin a contract test that detects upstream drift. | 'Reused verbatim' is a copy dependency, not an abstraction; it will diverge. The guided experience is the most user-visible surface — silent routing changes are high-impact. | M0 milestone; add a note or a contract test reference | Test: any change to `concierge_agent.py:59-75` that alters ladder semantics fails a contract test owned by the guided experience routing seam. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-S3: Splitting M3 into M3a (promote + behavioral-equivalence gate) and M3b (harden) is essential; promotion regression and hardening regression must be distinguishable.
- R1-S4: Blocking M3 start on OQ-GE-8 is the right gate; the abstraction shape is the riskiest unknown.
- R1-S6: A CI write-audit mechanism (not a manual claim) is the only durable "one write path" enforcement.
- R1-S8: Cloud Deepen + static API key + real LLM spend is a genuine abuse/cost surface; must be resolved before M5 ships.
- R1-S11: SOTTO residue test (engaged-then-disengaged) is the dangerous case and R1 correctly identifies it is not covered by the current never-engaged assertion.

---

#### Review Round R1 — claude-opus-4-8 — 2026-07-04

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-04 17:40:00 UTC
- **Scope**: Independent architectural review of the implementation plan (S-prefix), weighted per the sponsor focus file (consolidation soundness, M3 facilitation promotion, routing edges, safe-write coverage, cloud scoping, plan↔requirements consistency). Settled items were not relitigated.

##### Sponsor focus asks (addressed first)

**Ask 1 — Consolidation soundness / M1–M2 sequencing.**
- **Summary answer:** Sequencing is mostly sound, but M1 retires the top-level groups *before* M2 does the actual detangle — the aliasing shim in M1 must not become the permanent state if M2 slips.
- **Rationale:** M1 says "alias their verbs under `kickoff` (hidden aliases for one release)"; M2 is the merge that makes the aliases real. If M2 is delayed, the release ships with hidden aliases pointing at un-merged code — the sprawl is hidden, not reduced. The '24 → ~16 modules' target in M2 is the load-bearing reduction, not M1's group-count change.
- **Suggested improvements:** R1-S1 (add an explicit M1↔M2 coupling / deprecation-removal gate), R1-S2 (state a rollback for M1 aliases if M2 slips).

**Ask 2 — M3 facilitation promotion (biggest lift).**
- **Summary answer:** The riskiest milestone is under-instrumented: no behavioral-equivalence gate between the script and the promoted module, and it starts before OQ-GE-8 is resolved.
- **Rationale:** M3 promotes then hardens in one milestone, but has no step asserting the promoted `facilitation.py` reproduces the script's behavior before hardening begins — so a promotion regression and a hardening regression are indistinguishable. M3 also depends on OQ-GE-8 (abstraction sizing), which is still open.
- **Suggested improvements:** R1-S3 (split M3 into M3a promote+equivalence-gate / M3b harden), R1-S4 (block M3 start on OQ-GE-8 resolution).

**Ask 3 — Routing / offer-not-force edges (M0).**
- **Summary answer:** M0 does not specify non-interactive/CI behavior or the agent-driven-served case.
- **Rationale:** M0's "one ignorable offer line" is undefined for piped/CI invocations and for a served surface an agent drives (surface-heuristic would offer). Precedence handles it in principle; M0 should encode it.
- **Suggested improvements:** R1-S5 (M0 acceptance: non-interactive ⇒ suppress offer; served-agent ⇒ preference-suppressed).

**Ask 4 — Safe-write coverage (M2/M3).**
- **Summary answer:** M2's "verify all writes ride `safe_write.py`" is the right gate but is unmeasured; M3 fixes the transcript-bypass but M0's own preference/config writes are never routed.
- **Rationale:** M2 asserts the verification but names no mechanism; M0 writes `build-preferences.yaml`/`config.json` with no stated floor routing.
- **Suggested improvements:** R1-S6 (add a repo-wide write-audit gate), R1-S7 (route M0 preference writes through the floor or document the exemption).

**Ask 5 — Cloud read-only (M5).**
- **Summary answer:** M5's read-only story is clean for *writes* but silent on cloud Deepen invoking paid LLM calls under a static API key.
- **Rationale:** M5 permits "Orient + Deepen-view" on cloud; FR-GE-10 H3 makes Deepen spend real money; cloud auth is a static key with no tenancy. Read-only ≠ cost-safe.
- **Suggested improvements:** R1-S8 (M5 must state whether cloud Deepen is static-transcript-only or gated by a per-tenant budget control).

**Ask 6 — Plan↔requirements gaps.**
- **Summary answer:** Two: the plan `Tracks: v0.2` but the requirements are v0.3, and FR-GE-14 is mapped to "all" with no concrete milestone step.
- **Rationale:** Version drift (R1-S9) and a safety invariant with no owning task (R1-S10) both weaken traceability.
- **Suggested improvements:** R1-S9, R1-S10 below.

##### Numbered suggestions (S-prefix)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Couple M1 and M2 explicitly: M1's hidden aliases carry a removal deadline tied to M2 completion, and 'consolidation' is not claimed done until M2's '24 → ~16 modules' lands. | M1 changes group *count* but the real detangle is M2; shipping M1 alone hides sprawl behind aliases and could be mistaken for the win. | M1 'Retire ... hidden aliases' bullet; add an M1↔M2 gate note | Track module count (24→~16) as the M2 done-criterion; assert aliases are removed by the stated release. |
| R1-S2 | Risks | medium | State a rollback/contingency for M1 if M2 slips: either hold M1 group-retirement until M2 is ready, or ship aliases with a tested fallback so users are never left with dangling verbs. | 'Hidden aliases for one release' assumes M2 lands in that release; no contingency if it doesn't. | M1 milestone | Test: every retired verb resolves (via alias) even if M2 code is not yet merged. |
| R1-S3 | Validation | high | Split M3 into **M3a (promote + behavioral-equivalence gate)** and **M3b (harden H1/H2/H3)**; M3b does not begin until a golden transcript proves the promoted module matches the script. | Promoting and hardening in one milestone makes a promotion regression indistinguishable from a hardening change; the equivalence gate is the safety net for the biggest lift. | M3 milestone (split) | Golden-file test (script vs promoted module, fixed seed) is the M3a exit gate. |
| R1-S4 | Risks | high | Block M3 start on OQ-GE-8 resolution (does the promoted module reuse `StakeholderPanel.ask_all` directly, or need its own multi-round abstraction?). | M3's promotion target shape is exactly what OQ-GE-8 leaves open; starting M3 first risks building the wrong abstraction and reworking. | M3 preamble; 'Guiding constraints' | Traceability: M3 tasks reference a RESOLVED OQ-GE-8; plan gate blocks otherwise. |
| R1-S5 | Interfaces | medium | M0 acceptance criteria must cover non-interactive (piped/CI, no TTY ⇒ suppress the offer, never block) and agent-driven-served (surface-heuristic offer is suppressed by an agent-set `--no-guided`/config). | M0's 'one ignorable offer line' is undefined for CI and wrongly offers to an agent serving the UI. | M0 milestone bullets | Tests: stdin-closed/stdout-piped run emits no offer, kernel bytes identical; served + `--no-guided` yields no offer. |
| R1-S6 | Ops | medium | M2's 'Verify all writes ride safe_write.py' needs a concrete mechanism: a repo-wide write-audit (grep/AST gate in CI for direct `open(..., 'w')`/`Path.write_*` in the kickoff domain) rather than a manual claim. | The 'one write path' invariant is only as strong as its enforcement; a manual verify decays. | M2 'Verify all writes' bullet | CI gate: fail on any non-safe-write file write under the kickoff/guided modules. |
| R1-S7 | Data | medium | M0 must route its own preference/config writes (`build-preferences.yaml`, `~/.startd8/config.json`) through the safe-write floor, or the plan must document why they are exempt. | M0 introduces new writes not covered by M2/M3's floor-routing; they are the first new write path since the detangle. | M0 milestone | Test: preference/config writes use the safe-write API; exemption (if any) is documented and traversal-tested. |
| R1-S8 | Security | high | M5 must specify whether cloud read-only permits LLM-invoking Deepen (real spend, static API key, no tenancy) or only static preview of persisted transcripts; if the former, gate it behind a per-tenant budget control. | 'Read-only' addresses writes but not cost/abuse; cloud Deepen can spend money under an unauthenticated-per-tenant surface. | M5 milestone | Test: cloud Deepen either serves only persisted transcripts (no LLM call) or is budget/auth-gated per caller. |
| R1-S9 | Architecture | low | Fix the version reference: plan `Tracks: GUIDED_EXPERIENCE_REQUIREMENTS.md v0.2` but the requirements header is v0.3. | A plan tracking a stale requirements version invites drift between the two docs. | Plan header 'Tracks:' line | Grep both docs; assert the plan tracks the current requirements version. |
| R1-S10 | Validation | medium | FR-GE-14 is mapped to 'all' milestones with no concrete task; add a dedicated step (provenance-marking + ratification-state on synthetic inputs) that some milestone owns and tests. | A safety invariant mapped to 'all' is owned by none; it needs a testable home (likely M2 write-path or M3 facilitation output). | FR→Milestone table; owning milestone | Test per R1-F10: synthetic inputs are provenance-tagged unratified and refused unratified by the kernel. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S11 | Risks | medium | Add a SOTTO regression gate: a golden test that runs the kernel, then a guided pass, then the kernel again, asserting byte-identical kernel outputs (catches residue from config/transcript writes left by a guided run). | The plan asserts 'kernel byte-identical when absent' but never tests the *engaged-then-disengaged* residue case, which is where the invariant historically breaks. | New line under 'Guiding constraints' or M0 | Golden test: kernel-only vs guided-then-kernel-only outputs are byte-identical. |
| R1-S12 | Ops | low | M4 (surface parity) needs a defined parity oracle scope: `concierge_view.py` is called 'the parity oracle', but the plan should state parity is of *produced inputs/artifacts*, not interaction modality (served UI can't run a TTY wizard step). | 'Differing only in rendering' overclaims; some phases are modality-bound, making a naive parity test impossible or vacuous. | M4 milestone | Parity test asserts identical produced artifacts across surfaces, not identical interaction steps. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — this is Round R1; no prior rounds exist.)

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement in `GUIDED_EXPERIENCE_REQUIREMENTS.md` v0.3 to the plan milestone(s) that address it. Coverage: **Full** / **Partial** / **Gap**.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-GE-1 (optional layer / SOTTO byte-identical) | M0 | Partial | Byte-identical is asserted for 'absent from start' but no milestone tests the engaged-then-disengaged residue case (see R1-S11 / R1-F11). |
| FR-GE-2 (available not required; complement) | M0 | Full | Offer-not-force encoded in M0; kernel unaffected. |
| FR-GE-3 (offer-not-force routing) | M0 | Partial | Non-interactive/CI behavior and agent-driven-served case unspecified (R1-S5 / R1-F4/F5). |
| FR-GE-4 (explicit override always wins) | M0 | Full | Precedence ladder reused verbatim; covered. |
| FR-GE-5 (one experience, not three metaphors) | M1 (+M2) | Full | Orient→Guide→Deepen sequencing over `build_kickoff_plan`; deterministic-first noted. |
| FR-GE-6 (same kernel; no new engine) | M2 | Partial | M2 merges modules but no explicit criterion asserting 'no new extractor/generator/writer/readiness' was introduced (anti-principle check unmeasured). |
| FR-GE-7 (one entry point / vocab / write path) | M1, M2 | Partial | Reduction targets are real, but no anti-re-accretion enforcement clause and no write-audit mechanism (R1-S1/S6, R1-F1). |
| FR-GE-8 (standalone first-class; cloud read-only) | M5 | Partial | Cloud read-only addresses writes but is silent on LLM-invoking Deepen cost/abuse under a static API key (R1-S8 / R1-F8). |
| FR-GE-9 (surface parity CLI/TUI/served) | M4 | Partial | 'Parity' undefined for modality-bound phases; oracle scope needs bounding (R1-S12 / R1-F12). |
| FR-GE-10 (facilitation hardening H1/H2/H3) | M3 | Partial | H2 halt not scoped away from the FR-GE-3 no-gate guarantee (R1-F7); H1/H3 covered. |
| FR-GE-11 (persist raw per-round transcripts) | M3 | Full | Raw-round persistence is an explicit M3 task, routed through the floor. |
| FR-GE-11a (promote facilitation, then harden) | M3 | Partial | No behavioral-equivalence gate; starts before OQ-GE-8 resolves (R1-S3/S4, R1-F2/F3). |
| FR-GE-12 (anti-smoothing as requirement/test) | M3 | Full | M3 makes tension-survival a test. |
| FR-GE-13 (all writes ride safe-write floor) | M2, M3 | Partial | Inputs+transcripts covered; M0's own preference/config writes not routed (R1-S7 / R1-F6); verification mechanism unspecified (R1-S6). |
| FR-GE-14 (produces inputs for ratification; never authors/decides) | 'all' | Gap | Mapped to 'all' with no owning task and no acceptance test (provenance/ratification unverifiable) (R1-S10 / R1-F10). |

## Requirements Coverage Matrix — R2

Analysis only (not triage). Second-pass coverage review; adds findings not in R1's matrix. Focus: operationalization gaps, cross-milestone dependencies, and acceptance-criterion completeness. Coverage values: **Full** / **Partial** / **Gap** (R2 deltas from R1 noted).

| Requirement | Plan Milestone(s) | Coverage | R2 Gaps / Notes |
| ---- | ---- | ---- | ---- |
| FR-GE-1 (SOTTO byte-identical) | M0 | Partial | R1 noted engaged-then-disengaged residue (R1-S11). R2 adds: the routing-ladder "reuse verbatim" (M0) creates a silent coupling — if `concierge_agent.py:59-75` changes, SOTTO behavior changes without a plan-side gate (R2-S7). |
| FR-GE-2 (available not required) | M0 | Full | No new gaps found. |
| FR-GE-3 (offer-not-force routing) | M0 | Partial | R1 caught CI/non-interactive and agent-served edges. R2 adds: ladder "reused verbatim" is a copy dependency without a contract test; upstream changes silently break routing semantics (R2-S7). |
| FR-GE-4 (explicit override always wins) | M0 | Full | No new gaps found. |
| FR-GE-5 (one experience, three functions) | M1 (+M2) | Partial | R1 called Full; R2 downgrades to Partial: "Deepen is optional" implies a mid-flow skip/exit path that no milestone owns or tests (R2-S5). |
| FR-GE-6 (same kernel; no new engine) | M2 | Partial | R1 noted missing criterion. R2 adds a concrete mechanism gap: the M2 detangle is the highest-risk window for accidental engine introduction, and no CI check is proposed (R2-S6). |
| FR-GE-7 (one entry point / vocab / write path) | M1, M2 | Partial | R1 noted anti-re-accretion gap. No new R2 gap; R1-F1 + R1-S6 cover this well. |
| FR-GE-8 (standalone first-class; cloud read-only) | M5 | Partial | R1 caught LLM-invoking Deepen cost/abuse. R2 adds: the M5-last sequencing hides a cross-milestone dependency — if cloud Deepen must be static-transcript-only, M3 must build a cloud-readable transcript format before M5; discovery post-M3 forces rework (R2-S4). Additionally, the "download-and-write-locally" path for cloud users is not specified: what format are downloaded inputs in, and how does the local CLI write honor FR-GE-13 when the SDK is not running locally? (partial gap, low severity). |
| FR-GE-9 (surface parity CLI/TUI/served) | M4 | Partial | R1 caught modality-bound parity definition gap. No new R2 gap. |
| FR-GE-10 (facilitation hardening H1/H2/H3) | M3 | Partial | R1 caught H2 scope. R2 adds: H1 grounding has no operationalized acceptance criterion (what constitutes "real system" vs "schema"? what is the fallback?) (R2-S3). H3 "wire cost_usd end-to-end" has no defined scope/surface (R2-S1). |
| FR-GE-11 (persist raw per-round transcripts) | M3 | Full | No new gaps; well-covered by M3 + safe-write floor routing. |
| FR-GE-11a (promote facilitation, then harden) | M3 | Partial | R1 noted behavioral-equivalence gap and OQ-GE-8 blocking. No new R2 gap on this item; R1-S3/S4/F2/F3 cover it. |
| FR-GE-12 (anti-smoothing as requirement/test) | M3 | Partial | R1 called Full; R2 downgrades to Partial: "named raw-round tensions must be present" requires a naming/tagging schema for tensions — without one, the assertion is prose-matching and cannot distinguish a tension preserved vs. a tension paraphrased away (no plan step addresses this; see R2-F1 in requirements doc). |
| FR-GE-13 (all writes ride safe-write floor) | M2, M3 | Partial | R1 noted config/preference writes and verification mechanism gaps. R2 adds: M2's chat-constructor collapse (R2-S2) is a write-path manipulation point — the parametrized constructor must not introduce a new write path outside the floor. |
| FR-GE-14 (produces inputs for ratification; never authors/decides) | 'all' | Gap | R1 called this a Gap correctly. R2 confirms: no milestone owns this. A provenance-marking step belongs in M3 (facilitation transcripts) and M2 (conductor outputs) at minimum. |

## Requirements Coverage Matrix — R3

Analysis only (not triage). Third-pass deltas over the R1/R2 matrices; rows without an R3 delta carry the prior verdict unchanged.

| Requirement | Plan Milestone(s) | Coverage | R3 Gaps / Notes |
| ---- | ---- | ---- | ---- |
| FR-GE-1 (SOTTO byte-identical) | M0 | Partial | No new R3 gap (R1-S11/R2-S7 stand). |
| FR-GE-2 (available not required) | M0 | Full | No new gaps. |
| FR-GE-3 (offer-not-force routing) | M0 | Partial | R3 adds: the reused ladder has no tri-state — falsy layers are skipped, so config-level force-off falls through (R3-S5 / reqs R3-F2). File path + key name for the guided preference unspecified. |
| FR-GE-4 (explicit override always wins) | M0 | Partial | **Downgraded from Full (R1/R2):** "always wins" is exactly the property the verbatim-reused ladder breaks for the force-OFF direction (falsy skip). Covered only once R3-S5's tri-state contract lands. |
| FR-GE-5 (one experience, three functions) | M1 (+M2) | Partial | Per R2 (Deepen early-exit unowned); no new R3 gap. |
| FR-GE-6 (same kernel; no new engine) | M2 | Partial | No new R3 gap (R2-S6 stands). |
| FR-GE-7 (one entry point / vocab / write path) | M1, M2 | Partial | R3 adds: metric omits the MCP `startd8_concierge` action vocabulary (parent FR-10 as amended requires MCP aliasing — R3-S2 / reqs R3-F5); headline numbers have no enumerated baseline (R3-S3); M2's module-count gate contradicts the requirement's own reframed metric (R3-S4). |
| FR-GE-8 (standalone first-class; cloud read-only) | M5 | Partial | No new R3 gap (R1-S8/R2-S4 stand). |
| FR-GE-9 (surface parity CLI/TUI/served) | M4 | Partial | R3 adds: post-M2 the plan names no surviving TUI surface for the parity test (R3-S6). |
| FR-GE-10 (facilitation hardening H1/H2/H3) | M3 | Partial | No new R3 gap (R1-F7, R2-S1/S3 stand). |
| FR-GE-11 (persist raw per-round transcripts) | M3 | Partial | **Downgraded from Full (R1/R2):** persistence is planned, but the transcript contract its shipped consumer reads (path/schema/round-by-round cadence — `KICKOFF_PANEL_OBSERVABILITY_UX_REQUIREMENTS.md` FR-UX-1/17) is not carried as an M3 constraint; an end-of-session atomic write satisfies M3 as written and breaks live-follow (R3-S1 / reqs R3-F4). |
| FR-GE-11a (promote facilitation, then harden) | M3 | Partial | No new R3 gap beyond the transcript-contract constraint above (R1-S3/S4 stand). |
| FR-GE-12 (anti-smoothing as requirement/test) | M3 | Partial | Per R2 (tension tagging schema); no new R3 gap. |
| FR-GE-13 (all writes ride safe-write floor) | M2, M3 | Partial | R3 adds: the floor's atomicity **granularity** is unspecified and load-bearing for the UX live-follow consumer (R3-S1). Config/preference-write and audit-mechanism gaps (R1) stand. |
| FR-GE-14 (inputs for ratification; never authors/decides) | 'all' | Gap | Confirmed Gap (R1/R2); no owning milestone yet. Reqs-side note: its provenance parentheticals cite parent review IDs that now collide with this doc-set's own IDs (reqs R3-F1). |
