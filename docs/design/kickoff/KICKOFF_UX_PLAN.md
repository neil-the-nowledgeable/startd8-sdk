# Kickoff UX / Information Architecture — Implementation Plan

**Version:** 0.2 (Post-CRP R1)
**Date:** 2026-07-02
**Requirements:** `KICKOFF_UX_REQUIREMENTS.md` (v0.4)
**Branch:** `feat/kickoff-ux-spec` (worktree off `origin/main`).

---

## Planning discoveries (feed the reflection pass)

| What v0.1 assumed | What planning (code read) revealed | Impact |
|-------------------|-----------------------------------|--------|
| The "four things" is a **new mental structure** to design | It maps **1:1 onto the existing 5 `STAGES`** (`data_model`/`manifests`/`value_inputs`/`content`/`run`) — the four things + Build ARE the five stages, just plain-renamed (content de-emphasized). | **FR-UX-1/6 simplify:** the spine is the **existing stages, glossary-renamed** — not a new structure. The redundancy fix = render the renamed spine **once** + attach one next action + completion; move advisories/playbook behind `--verbose`. |
| A glossary may already exist somewhere (OQ-1) | **None exists** — no plain-name/`display_name`/`GLOSSARY` anywhere in `kickoff_experience/`. | **OQ-1 → net-new.** Add a small **presentation module** owning the single-source glossary + the stage→plain-name map + the spine/headline builder. This is the concrete deliverable. |
| `--verbose` toggles depth (OQ-3) | `red-carpet` has only `--json`/`--check`/`--wizard`/`--agent` — **no `--verbose`**. | **OQ-3 → add `--verbose`** (a bool option; Typer convention). Default view = focused; `--verbose` = advisories + playbook. |
| The status "one next action" comes from `ranking.next_action` (OQ-4) | `next_action` (unified via `blocker_cta`) reads "Resolve readiness blocker: **Services**" (jargon); the **advisor playbook rank-1** reads the plain-er **"Author the data-model contract"** (`build_playbook:459`). | **OQ-4 → use `next_steps[0]`** (playbook rank-1), glossary-translated, for the headline action. |
| Two %s both matter (OQ-5) | `completion.overall_pct` (FR-WD-2) is the "how done am I" number; `readiness_score` is a coarse ready-*stage* fraction. | **OQ-5 → headline = `completion.overall_pct`**; readiness drops from the headline (→ `--verbose`, labeled). |
| Greenfield-calm needs advisory data changes (OQ-6) | Derivable at render time: `completion.overall_pct == 0` AND schema absent ⇒ "not started". The alarming "Cascade blocker" lines are already `warn` advisories — they just dominate the default view. | **OQ-6 → presentation-only.** Greenfield headline = calm "begin with Your data"; cascade-blocker advisories move behind `--verbose`. No advisory-data change. |
| The wizard's status wall needs a driver change (FR-UX-9) | The CLI wrapper passes the full-wall render; swapping it fixes the *wall*. **BUT (CRP R1-S1/S2):** the found/needed/action *lines* are emitted by the **driver** with raw stage keys, and the driver calls `render_state(state)` before the action exists. | **FR-UX-9/10 corrected:** swap the render (consuming `state`) **and** glossary-translate `found`/`needed` at `WizardAction` construction in `wizard.py`. "No driver change" was too strong; the change stays inside the wizard module's presentation surface. |

**Net:** the spec is almost entirely **presentation** over unchanged mechanisms — one new small module +
a `--verbose` flag + render swaps. The biggest "aha" is that the four-things model already exists as the
5 stages; we rename, don't restructure.

---

## Approach & step map

### Step 1 — The presentation module (FR-UX-1/2/3/6) — the single source
- New `src/startd8/kickoff_experience/presentation.py` (surface-neutral, `$0`):
  - `GLOSSARY` — the one plain-name map: `{"data_model":"Your data", "manifests":"Your screens",
    "value_inputs":"Your settings", "content":"Placeholder content", "run":"Build"}` + a `WHAT_IS`
    one-liner per thing. **Single source** all surfaces cite (FR-UX-2).
  - `build_spine(state) -> list[SpineNode]` — the three-things + Build spine from `state.stages` /
    `next_stage` / `completion`: each node = `{key, plain_name, status, detail?}`. **Build uses a distinct
    terminal status `ready` (never `done`)** since `run.status=="done"` means offerable, not built (CRP
    R1-F1). `content` flagged `later` + de-emphasized (an optional add-on, not a peer).
  - `headline(state) -> {pct, plain, you_are_here, next_action, warn_banner?}` — the completion % labeled
    **"% filled"** (FR-UX-7); **not-yet-buildable annotation** ("100% filled · not yet buildable") when an
    error advisory / unmet gate persists, and "· N defaulted — review" when filled == defaulted (CRP
    R1-F3); the single next action from `next_steps[0]` glossary-translated (FR-UX-4); the **calm
    greenfield** variant when `overall_pct==0` + schema absent (FR-UX-8); and an **error banner** count of
    `severity=="error"` advisories (never hidden — CRP R1-F4).

### Step 2 — Rewrite the status view (FR-UX-4/5/6/7/8; CRP R1-S3/S4/S5)
- `cli_kickoff._render_red_carpet_state(state, *, verbose=False)`: default = the spine (once) + headline
  (one % + not-yet-buildable annotation) + **the error banner if any** (CRP R1-S4 — never hidden) + the
  single next action + a "N more → `--verbose`" pointer. **Remove** the parallel Insights + Next-steps
  dumps from the default path. Under `verbose=True`, append the full advisories + playbook, plain-labeled.
- **Glossary-translate the completion meter (CRP R1-S3):** the meter today prints raw keys
  (`f"{s['stage']} {s['filled']}/{s['total']}"`) — render via `GLOSSARY` ("Your data 0/1"), and **collapse
  settings to a single subordinate line** ("Your settings · 2 of 8", CRP R1-S5/FR-UX-3).
- Add `verbose: bool = typer.Option(False, "--verbose")` to `red_carpet_cmd`; thread it in. `--json`
  unchanged (NR-3).

### Step 3 — Compact wizard render (FR-UX-9/10; CRP R1-S1/S2 — corrects "no driver change")
- **Glossary-translate at construction (CRP R1-S2):** the driver emits `found`/`needed` with raw stage
  keys, so translate them **where the `WizardAction` is built** in `wizard.py::wizard_prepopulate`
  (presentation-only, inside the wizard module) — swapping the render alone cannot reach them.
- New `presentation.render_wizard_step(state) -> lines` — **consumes `state`** (CRP R1-S1: the driver calls
  `render_state(state)` before the action exists), rendering the compact spine ("Step N of M · plain name")
  from `state`. In `_run_red_carpet_wizard`, pass it as `render_state` **instead of**
  `_render_red_carpet_state`; drop the opening full wall — one framing line, then step-by-step.

### Step 4 — Help text / mode roles (FR-UX-11)
- Reword `red-carpet` help so each mode's role is one line: default = *glance*, `--wizard` = *do*,
  `--agent` = *talk*, `--json`/`--verbose` = *detail*.

### Step 5 — Cross-surface note (FR-UX-12)
- The web rail (`web.py`) is out of scope to rebuild here (NR-4), but the glossary + `build_spine` are
  importable by it; add a short docstring/pointer so the later web wizard consumes the same module. No web
  code change this increment.

### Step 6 — Tests + snapshots
- `presentation.py`: glossary covers all 5 stage keys; `build_spine` — **Build renders `ready`, never `✓
  done`, for an offerable-but-never-built project** (CRP R1-F1); content de-emphasized; `headline` labels
  "% filled" + **"not yet buildable"** for a present-unparseable schema and **"N defaulted — review"** for
  all-defaulted (CRP R1-F3); greenfield-calm variant; next action = `next_steps[0]` translated.
- **No-jargon guard (non-gameable, CRP R1-F2/S3):** run over **both** the default AND `--verbose` output
  AND `next_steps[0].detail/.command`; token set `{cascade, manifest, value_path, prisma, schema,
  @relation, @@id, provenance, gate, bookend, buckets}`. A jargon token planted in an advisory `detail`
  **fails** even when advisories are behind `--verbose`. The completion meter shows "Your data 0/1", not
  "data_model 0/1".
- **Error-not-hidden (CRP R1-F4/S4):** an invalid-input project shows a default **error banner** ("1
  problem → --verbose"); the default view and `--check` exit agree.
- **Settings right-size (CRP R1-F5/S5):** snapshot — settings is a single subordinate line ("Your settings
  · N of 8").
- Wizard: the compact step view contains the spine + one step and **not** the full wall (snapshot); wizard
  `found/needed` copy contains no raw `data_model`/`value_inputs`/`prisma` tokens (CRP R1-S2).
- `--json` byte-unchanged (regression); all kickoff suites green.

---

## §7 Validation Strategy
- **Focus proof:** default `red-carpet` output ≤ ~12 lines and contains exactly one "do next" action.
- **No-jargon proof:** default + wizard rendered strings contain none of the internal-vocabulary terms
  (glossary is the only naming path).
- **Say-once proof:** a given gap string appears at most once in the default view.
- **Backward compat:** `--json` unchanged; `--verbose` reproduces today's detail; all kickoff suites green.
- **Calm greenfield:** a blank project's headline is informational (not error-colored) and says "begin
  with Your data".

## Risks
- **R1 — Hiding real problems behind `--verbose`.** Mitigation (corrected, CRP R1-S4): `--verbose` is
  additive **except** `severity=="error"` advisories, which **stay in the default view as a banner** —
  because `next_steps[0]` is dependency-ordered, an error below an unmet gate would otherwise surface
  nowhere. The default human view and `--check` therefore agree.
- **R2 — Glossary drift** if surfaces re-name locally. Mitigation: single-source `GLOSSARY` (FR-UX-2) + the
  no-jargon test; no surface hardcodes a plain name.
- **R3 — Snapshot brittleness.** Mitigation: assert on presence/absence of key tokens, not exact layout.

---

*v0.2 — Post-CRP R1 (all 6 S accepted). Hardened: render_wizard_step consumes `state` + translate at
`WizardAction` construction (R1-S1/S2 — "no driver change" corrected); glossary-translate the completion
meter (R1-S3); error advisories stay in the default banner (R1-S4); FR-UX-3 settings right-sizing gets a
step + snapshot (R1-S5); requirements pointer synced to v0.4 (R1-S6). F-side dispositions in the
requirements Appendix A.*

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

> Triage R1 (orchestrator, 2026-07-02). **All 6 S accepted; none rejected.**

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | render_wizard_step consumes `state` | CRP R1 | Step 3 | 2026-07-02 |
| R1-S2 | translate found/needed at WizardAction (driver-change reality) | CRP R1 | Step 3 + discovery row | 2026-07-02 |
| R1-S3 | glossary-translate the completion meter | CRP R1 | Step 2 | 2026-07-02 |
| R1-S4 | error advisories stay in default banner | CRP R1 | Step 2 + Risk R1 | 2026-07-02 |
| R1-S5 | operationalize FR-UX-3 settings right-sizing | CRP R1 | Step 2 + Step 6 | 2026-07-02 |
| R1-S6 | sync requirements pointer to v0.4 | CRP R1 | plan header | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 23:45:00 UTC
- **Scope**: Plan review for the Kickoff UX/IA spec, weighted per the sponsor focus file. Grounded in `wizard.py`, `cli_kickoff.py`, `red_carpet.py`, `red_carpet_advisor.py`, `red_carpet_completion.py`.

##### Executive summary

- **Blocking integration gap:** Step 3's `render_wizard_step(action, spine)` cannot be wired as the driver's `render_state(state)` callback — the driver passes `state`, not `action`, and computes the action *after* the render call (`wizard.py:194,198`).
- **"No driver change" is false for FR-UX-10:** the jargon-bearing found/needed/action lines are emitted by `run_red_carpet_driver` itself (`wizard.py:210-213`), not by the swappable render — glossary translation requires touching the driver or the `WizardAction` construction.
- **Progressive disclosure hides errors:** Step 2 moves advisories behind `--verbose`, but `severity=="error"` advisories are exactly what `--check` fails on — the human default view and CI would disagree.
- **Completion-meter jargon:** the existing meter renders raw stage keys (`cli_kickoff.py:221`) — Step 2 must glossary-translate these or the no-jargon proof fails on the default path.
- **Headline honesty:** Step 1's `headline` reads `completion.overall_pct`, which is present-based not validity-based — needs a not-yet-buildable annotation.
- **FR-UX-3 has no plan step:** settings right-sizing is asserted but not built or tested.

##### Plan Suggestions (first pass)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | critical | Fix Step 3: define `render_wizard_step` to consume the driver's `state` (compute the compact spine + current step from `state`), since `run_red_carpet_driver` calls `render_state(state)` at `wizard.py:194` before the action exists (`:198`). Passing `(action, spine)` cannot be wired. | The signature in Step 3 is incompatible with the driver's `render_state: Callable[[Any], None]` contract; as written the swap won't compile into the loop. | Step 3 (Compact wizard render) | Wire the callback in `_run_red_carpet_wizard`; a wizard run renders the compact step with no arg-mismatch. |
| R1-S2 | Architecture | high | Correct the "swap the render callback — no driver change" premise: the found/needed/action lines are emitted by the driver (`wizard.py:210-213`) with raw stage keys. To satisfy FR-UX-10, glossary-translate `found`/`needed` at `WizardAction` construction (in `wizard.py`) or change the driver's emit lines. | FR-UX-10 (plain-language step copy) is unreachable by swapping `render_state` alone; the plan's own §0 discovery understates the change surface. | Step 3 + Planning-discoveries row for FR-UX-9 | Snapshot: wizard step copy contains no raw `data_model`/`value_inputs`/`prisma` tokens. |
| R1-S3 | Validation | medium | Step 2 must glossary-translate the per-stage completion meter, which today prints raw keys: `f"{s['stage']} {s['filled']}/{s['total']}"` (`cli_kickoff.py:221`). Otherwise the default status view still emits `data_model`/`value_inputs` and fails the no-jargon proof. | The say-once/no-jargon proofs (Step 6 / §7) scan the default view, which includes this line. | Step 2 (Rewrite the status view) | No-jargon test asserts the meter shows "Your data 0/1", not "data_model 0/1". |
| R1-S4 | Risks | high | Amend Risk R1 mitigation: `--verbose` must be additive **except** for `severity=="error"` advisories, which stay in the default view (count/banner). The current mitigation ("the one next action surfaces the top gap") does not hold — `next_steps[0]` is dependency-ordered (`build_playbook:457-467`), so an error advisory below an unmet gate surfaces nowhere. | Aligns the default human view with `--check` (`cli_kickoff.py:359`); prevents a silently-broken input from being hidden. | Risks §R1 + Step 2 | Test: invalid-input project shows a default error signal; `--check` exit and default view agree. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Validation | medium | Add a plan step (or fold into Step 1/2) that operationalizes FR-UX-3 settings right-sizing with a concrete render rule + a test; today no step builds or verifies it. | Coverage gap: FR-UX-3 maps to no step, so it will silently not ship. | New sub-step under Step 2; Step 6 tests | Snapshot asserts settings render is a single subordinate line. |
| R1-S6 | Ops | low | Sync the plan front-matter (`**Requirements:** … (v0.1)`) to requirements v0.3 so the pair reviews against the same baseline. | Stale version pointer; the requirements doc has advanced through lessons-hardening to v0.3. | Plan header | Grep: both docs cite the same version. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each FR-UX-* to the plan step(s) that implement it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-UX-1 (four-things mental model) | Step 1 (`build_spine`) | Partial | `run`→Build renders as ✓done when merely offerable; `content` presented as an equal fourth thing though it is always-pending/uncounted (R1-F1). |
| FR-UX-2 (single glossary + no-jargon) | Step 1 (`GLOSSARY`), Step 6 (no-jargon test) | Partial | Glossary renames stage keys only; free-text advisory/playbook jargon passes through; the no-jargon test is default-only and gameable by hiding (R1-F2, R1-S3). |
| FR-UX-3 (right-size settings) | — | Missing | No step builds or tests settings right-sizing (R1-F5 / R1-S5). |
| FR-UX-4 (focused summary + one next action) | Step 1 (`headline`), Step 2 | Partial | `next_steps[0]` detail/command may carry jargon into the headline; plan doesn't say whether title/detail/command is shown (R1-F2). |
| FR-UX-5 (progressive disclosure) | Step 2 (`--verbose`) | Partial | Hides `error`-severity advisories, disagreeing with `--check` (R1-F4 / R1-S4). |
| FR-UX-6 (one spine, no triple redundancy) | Step 1, Step 2 | Full | — |
| FR-UX-7 (reconcile the two %s) | Step 1 (`headline`), Step 2 | Partial | `overall_pct` is presence-based, not validity/buildability-based; can read 100% for an unbuildable/all-defaulted project (R1-F3). |
| FR-UX-8 (calm greenfield) | Step 1 (greenfield variant) | Partial | "Calm" must not suppress error advisories (R1-F4). |
| FR-UX-9 (one step at a time) | Step 3 | Partial | `render_wizard_step(action,spine)` signature can't wire to the driver's `render_state(state)` (R1-S1). |
| FR-UX-10 (plain-language step copy) | Step 3 | Partial | Jargon lines are emitted by the driver, not the swappable render — unreachable by render swap alone (R1-S2). |
| FR-UX-11 (mode roles) | Step 4 (help text) | Full | — |
| FR-UX-12 (surface-neutral IA reused by web) | Step 5 (docstring/pointer) | Full | — (web build correctly out of scope, NR-4). |
