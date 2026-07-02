# Red Carpet Wizard-Driver + Asset-Chaining — Requirements

**Version:** 0.4 (Post-CRP R1)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `RED_CARPET_WIZARD_DRIVER_PLAN.md`
**Extends (do not duplicate — cite, don't re-spec):** `RED_CARPET_TREATMENT_REQUIREMENTS.md` (v0.3, the
gap-loop conductor), `RED_CARPET_PRESCRIPTIVE_ADVISOR_REQUIREMENTS.md` (v0.5, the ranked playbook +
insights), `INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (v0.5, FR-5 pre-populate / FR-11 guided
next-step / §F Phase-2), `KICKOFF_AUTHORING_CONTRACT.md`.

> **What this adds.** Today the Red Carpet experience is **reactive**: the `--agent` REPL blocks on the
> user each turn and lets the LLM decide ordering; the advisor *computes* a ranked playbook but nothing
> *drives* the user through it, and the SDK's own asset-inventory/derivation primitives (`survey`,
> `derive`, extraction) are **never chained** into the conductor to pre-populate. This increment adds a
> **deterministic ($0) proactive driver** that (a) inventories existing project assets and **proposes
> pre-populated inputs** from them, (b) **leads** the user step-by-step through the ranked playbook with
> a **completion meter**, and (c) falls back to the agentic interview only for gaps no asset can fill.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass caught a real **arbitrary-code-execution** landmine in the headline "derive schema
> from Pydantic models" feature and de-risked it, plus simplified two other requirements onto existing
> safe seams. The headline holds — this is a `$0` driver + pre-populate pass over the shipped conductor.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Auto-chain `survey → derive` to propose a schema from Pydantic models (FR-WD-5) | `derive-contract` needs **model IMPORT PATHS** and `introspect_models` **imports the actual classes** (`introspect.py:213`); `survey` returns **file paths**. Auto-deriving = **importing untrusted project code in the wizard** (ACE on import). | **FR-WD-5 reframed (security):** the driver **proposes the `derive-contract` command** with the discovered models identified; it **never imports project code**. The human runs the import at their privilege. |
| PRD→brief needs a new extraction path (FR-WD-6) | The `brief` proposal kind already writes `REQUIREMENTS.md` from a `source` prose string (no-clobber). Reading a PRD is `$0`/safe. | **FR-WD-6 simplified:** propose the PRD's content as the `brief` `source`; no new extraction/kind. |
| The driver modifies `run_red_carpet_repl` (FR-WD-1) | The REPL is pure/IO-injected and **blocks on `read_input` first**; the LLM sequences. A `$0` *leading* driver is a **new loop** reusing `on_proposal`/`render_state` without `ask_sync`. | **FR-WD-1 reframed:** a **new deterministic driver**; the REPL stays as the agentic fallback (FR-WD-8). |
| New proposal kinds needed (OQ-5) | `PROPOSAL_KINDS` is a **closed allow-list** (advisor CRP R1-F1 floor). FR-WD-6/7 reuse `brief`/`capture`; FR-WD-5 (propose-the-command) needs none. | **OQ-5 → no new proposal kind** (keeps the security floor intact). |
| Completion denominator = `writable_fields()` (OQ-3) | That covers only the 4 value-input domains; schema/app/pages/views are gates, not fields. | **OQ-3 → union model:** per-stage progress over `{cascade gates} ∪ {writable fields}`. |

**Resolved open questions:** OQ-1 → `$0` driver-first (new loop; interview is a per-gap sub-step). OQ-2 →
survey gives file paths, derive needs import paths + imports code → **propose the command, don't import**.
OQ-3 → union completion model. OQ-4 → the `brief` kind writes `REQUIREMENTS.md` from a `source`; PRD→brief
= propose the PRD as that source. OQ-5 → no new proposal kind. OQ-6 → advance only on a confirmed-OK
outcome + a no-progress guard (Interactive §F R2-F9).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons before CRP. Each changed or hardened the draft:

- **[Leg-1 #5 — Vocabulary drift / single-source ownership]** — this doc extends **four** specs and reuses
  their vocabulary, the top drift risk. Fix: an explicit **ownership split** (below). This doc **owns
  only** its new concepts — *wizard-driver*, *completion model*, the *found/needed/action* step triple.
  Everything else is **cited, non-normative snapshot**: the proposal kinds + closed-allow-list are owned by
  `proposals.py` / `RED_CARPET_TREATMENT_REQUIREMENTS.md`; the principles (P2 propose-confirm, P5 gap-loop)
  by RCT; the advisor playbook / `next_steps` by `RED_CARPET_PRESCRIPTIVE_ADVISOR_REQUIREMENTS.md`; FR-5/
  FR-11 by `INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md`. This doc must not re-define any of them.
- **[Phantom-reference audit]** — every code symbol named was grepped and exists (see §Reference-Audit);
  no to-be-created symbols are asserted as existing.
- **[CRP steering memory]** — the two new docs (this + the plan) are the **least-reviewed** artifacts →
  the CRP target. Settled / do-not-relitigate (carried to the CRP focus file, not re-argued here): the
  propose-confirm floor + closed-allow-list, RCT P5 "gap-loop not fixed wizard," and the **FR-WD-5 no-import
  security decision** (the wizard never imports project code).

### Reference-Audit

| Symbol | Owning module (verified present) |
|--------|----------------------------------|
| `build_red_carpet_state` / `run_red_carpet_repl` / `_CASCADE_GATE_KEYS` / `next_steps` | `kickoff_experience/red_carpet.py` + `red_carpet_advisor.py` |
| `build_survey` (`model_files`) | `concierge/core.py` |
| `introspect_models` / `derive-contract` | `concierge/derive/` |
| `PROPOSAL_KINDS` / `_apply_brief` / `build_capture_plan` | `kickoff_experience/proposals.py` / `capture.py` |
| `default_config().writable_fields()` | `kickoff_experience/manifest.py` |

*New symbols this doc introduces (to-be-created, marked as such): `run_red_carpet_driver`,
`build_completion`, `wizard_inventory`, `wizard_prepopulate`.*

---

## 1. Problem Statement

The proactive *analysis* shipped (advisories + ranked `next_steps` playbook + `prescriptive_banner`); the
proactive *conduct* did not. Three concrete gaps:

| Capability | Current State | Gap |
|-----------|--------------|-----|
| **Driving the user** | `run_red_carpet_repl` blocks on `read_input` first; the LLM sequences from prose (`RED_CARPET_SYSTEM_PROMPT`). Only `prescriptive_banner` (turn 0) leads. | No deterministic driver that leads with the playbook, presents each step, and auto-advances — the experience is user-blocked free-form chat. |
| **Leveraging assets** | `survey` discovers Pydantic models / PRD docs / fixtures; `derive` turns models → a `$0` candidate schema; extraction turns prose → manifests; `default_config().writable_fields()` enumerates fields. **None are auto-chained** by the conductor. | The advisor only *diagnoses* the gap ("no data model yet"); nothing proposes the schema the project's own Pydantic models could derive, or pre-fills fields from existing inputs. |
| **Completion sense** | `readiness_score` is a coarse ready-*stage* fraction; `stage.status` is binary. | No filled/total completion-% over the real field surface, so the user can't see "you're 60% done" or what remains. |

**What should exist:** a **deterministic `$0` wizard-driver** for Red Carpet that, on entry, **inventories
assets and proposes pre-populated inputs** (derived schema, extracted brief, pre-filled fields — each a
**proposal the human confirms**), then **leads** the user through the remaining ranked playbook with a
**completion meter**, using the agentic interview only where no asset can pre-fill the gap.

---

## 2. Guiding Principles (inherited — cite, don't re-litigate)

- **P1 — Determinism first / `$0`.** The driver, the asset-chaining, and the completion meter are all
  deterministic and `$0`. The LLM interview is the *fallback* for un-derivable gaps, not the driver.
- **P2 — The loop proposes; the human applies (non-negotiable).** Every pre-populated input — derived
  schema, extracted brief, pre-filled field — is a **proposal** the human confirms at human privilege
  (existing `propose_action`→`apply_proposal` seam). The driver **never writes**; MCP stays read-only.
- **P3 — Honor "gap-loop, not fixed wizard" (RCT P5).** This is a **proactive driver over the existing
  gap model**, not a rigid linear wizard. It *leads* but stays resumable, skippable, and keyed to the
  live `build_red_carpet_state` — a hand-edit or brownfield partial state re-orders it, never deadlocks it.
- **P4 — Translate, don't invent (Interactive P4).** When assets exist (Pydantic models, PRDs, inputs),
  the driver reformats/derives them into proposals; it never asks the user to retype what is on disk.
- **P5 — Extend, don't duplicate.** Reuse `build_red_carpet_state`, the advisor playbook, `survey`,
  `derive`, extraction, `capture`, and the propose-confirm seam. This adds a **driver + a pre-populate
  pass + a completion model** — no new grammar, extractor, or write engine.

---

## 3. Requirements

### A. The proactive driver

- **FR-WD-1 — A deterministic wizard-driver** *(reframed by planning)*. A **new** `$0` driver loop
  (`run_red_carpet_driver`, pure/IO-injected like the REPL, but **without** the `ask_sync` LLM turn) that
  leads over `build_red_carpet_state`: it presents the **current step** (ranked `next_steps` rank-1),
  states "found / gap / do this", offers the pre-populated proposal(s), and advances per the
  **outcome→advance mapping** (CRP R1-S3): advance on `ProposalOutcome.ok`; on a **retriable** outcome
  (`STALE_FILE`/`WRITE_BLOCKED`/`PARTIAL`, `_RETRIABLE_CODES`) **retain the step, do not advance, and do
  not count toward the no-progress threshold**; a decline/skip increments the no-progress counter. It does
  **not** modify `run_red_carpet_repl` (the agentic fallback, FR-WD-8). CLI: `startd8 kickoff red-carpet
  --wizard`. The step/completion model is surface-neutral (web later).
- **FR-WD-2 — Completion meter.** Add a real **filled/total completion model** over the **user-fillable**
  surface, `--json` + driver-surfaced, distinct from `readiness_score`.
  - **Denominator (CRP R1-F1):** user-fillable units only — `{cascade gates: schema/app/pages/views} ∪
    {writable value-input fields, `default_config().writable_fields()`}`. The `content` (always-pending
    "later") and `run` (derived) stages are **excluded** so a fully-filled project reads **100%**.
  - **Weighting (CRP R1-F2):** **stage-equal, then field-equal within a stage** (each stage contributes an
    equal share of the overall %; within a stage, its units split evenly) — so one whole-schema gate is not
    equal-weighted against one scalar field. The formula is stated and hand-count-testable.
  - **Filled semantics (CRP R1-F7):** a field is "filled" only if **present AND valid** — a present-but-
    invalid value (`input-invalid` advisory / round-trip failure) counts as **unfilled**, never masking a
    blocked build. **`defaulted` values are counted distinctly** ("N defaulted — review"), not as fully done.
- **FR-WD-3 — Step presentation contract.** For each step the driver renders a structured
  **found / needed / action** triple: what the pre-populate pass derived (with provenance), what is still
  missing, and the next action — **bound to a concrete `PROPOSAL_KINDS` member** (`brief`/`capture`/…) **or
  a named command** (CRP R1-F8), never free prose, so the action is testable against the closed allow-list.

### B. Asset-chaining (pre-populate as proposals)

- **FR-WD-4 — Auto asset inventory on entry.** On driver start, run the existing `survey` (read-only,
  `$0`, path/name heuristics only) and surface the discovered assets: Pydantic model files, PRD/
  requirements docs (and whether each matches the extraction format), existing inputs, fixtures. This is
  the source inventory the driver's proposals draw from (Interactive FR-5 source-inventory, pulled forward).
- **FR-WD-5 — Propose the derive *command* for discovered Pydantic models** *(reframed — SECURITY)*. When
  `survey` finds Pydantic model files and no confirmed `schema.prisma`, the driver **proposes the
  `concierge derive-contract` / `generate contract` action with the discovered model files identified** —
  a guided next step the human runs at their own privilege. The wizard **MUST NOT import or introspect the
  project's Pydantic modules itself** (importing untrusted project code = arbitrary-code-execution). The
  derive (which imports the user's own code) happens under the human's hand, not inside the driver.
  - **Framing note (CRP R1-F5):** the *proposed* `derive-contract` is itself already **subprocess-contained
    / fail-closed** (FR-DC-14: scrubbed-env, timeout-bounded — `concierge/derive/containment.py`,
    `_introspect_subproc.py`); the wizard's stance is narrower still — it does not even run that subprocess,
    it names the command. Cite this so the ACE framing is precise, not an overstatement of the derive path.
  - **Acceptance (discriminating, CRP R1-F4):** a positive AND negative assertion — the wizard **did**
    survey the model file **and emitted the derive-command proposal naming it**, **and** the import-time
    sentinel is **untouched**. (A wizard that errors early / never targets the model must **fail**, not
    pass vacuously.)
- **FR-WD-6 — Propose a brief from an existing PRD** *(simplified by planning)*. When `survey` finds a
  requirements/PRD doc and no confirmed brief, the driver **proposes a `brief` action whose `source` is the
  PRD's content** (the existing `brief` kind writes `docs/kickoff/REQUIREMENTS.md`, no-clobber). **Re-drive
  self-reference guard (CRP R1-F6):** `survey` globs `**/*REQUIREMENTS*.md`, which re-lists the brief's own
  output; FR-WD-6 must **exclude `docs/kickoff/REQUIREMENTS.md` from PRD detection** and **skip the proposal
  once the brief gate is met**, so the driver never re-proposes a brief from the file it just wrote.
- **FR-WD-7 — Pre-fill value-input fields** *(scoped by planning — capture replaces, cannot create)*. For
  value-input steps, the driver **proposes** field values pre-filled from the seeded `default_config`
  defaults (each a confirmable `capture`). **Precondition (CRP R1-F3/S4):** `build_capture_plan`/
  `splice_yaml_value` **replace an existing scalar** — they raise `TARGET_FILE_MISSING` for an absent domain
  file and `KEY_NOT_FOUND` for an absent key. So pre-fill is offered **only after `instantiate`** has
  scaffolded the inputs package and **only for fields whose template already seeds the dotted key**; when
  the package is absent the driver proposes `instantiate` first (not a failing capture). A capture for an
  unseeded key returns the typed `KEY_NOT_FOUND` (documented, not a crash).
- **FR-WD-8 — Fallback to the interview only for un-derivable gaps.** Where no asset can pre-fill a gap,
  the driver hands to the existing agentic interview (the one paid surface) for that step only — the
  driver stays in control of sequencing.

### C. Boundaries & cross-cutting

- **FR-WD-9 — Resumable / brownfield-safe.** The driver is a projection of the live state (like
  `build_red_carpet_state`): leaving and resuming re-derives the current step; a hand-edit between steps
  moves it to the correct live gap; it never forces the user back through a completed step (P3).
- **FR-WD-10 — Observability.** The driver emits the existing kickoff funnel events (step entered,
  proposal made/confirmed, asset-derived-proposal offered/accepted) with bounded attrs; add a
  `wizard_step`/completion-% signal for a completion/dropoff dashboard (reuse the RCA telemetry pattern).

---

## 4. Non-Requirements

- **NR-1 — Not a new grammar / extractor / write engine.** Reuses `survey`/`derive`/extraction/`capture`/
  the propose-confirm seam.
- **NR-2 — Not a rigid linear wizard.** No forced next/back; honors RCT P5 (gap-loop). "Wizard" here =
  proactive driver, not a lockstep form.
- **NR-3 — Not LLM-authored content.** Pre-populated proposals are `$0` derivations/extractions from
  existing assets, never invented real content (bucket-4). AI estimates are never silently promoted.
- **NR-4 — No autonomous / loop writes; MCP read-only.** The driver proposes; the human applies.
- **NR-4a — The wizard never imports/executes project code.** Asset inventory is path/name heuristics
  (`survey`); schema derivation (which imports Pydantic modules) is a **command the human runs**, never an
  in-wizard import. No arbitrary-code-execution surface (planning security discovery).
- **NR-5 — Not a replacement for `kickoff check` or the cascade.** It drives to a build-ready input
  surface; the `$0` cascade and the checker are unchanged.
- **NR-6 — Not the Interactive web-visual build.** This is CLI-first over the shipped conductor; the
  Interactive spec's web-visual/Phase-2 items (golden snapshots, WCAG suite, batch review) are out of
  scope here (the completion model is designed to feed them later).

---

## 5. Open Questions

*All 6 resolved by the planning pass — see §0.*

- **OQ-1 — RESOLVED → `$0` driver-first.** A new deterministic loop leads; the agentic interview is a
  per-gap sub-step (FR-WD-1/8). Not a REPL edit.
- **OQ-2 — RESOLVED (security) → propose the command, don't import.** `survey` gives file paths; `derive`
  needs import paths + imports the classes → the wizard proposes `derive-contract`, never imports (FR-WD-5).
- **OQ-3 — RESOLVED → union completion model** over `{cascade gates} ∪ {writable value-input fields}`,
  per-stage (FR-WD-2).
- **OQ-4 — RESOLVED → the `brief` kind writes `REQUIREMENTS.md` from a `source`;** PRD→brief = propose the
  PRD content as that source (FR-WD-6). No new extraction.
- **OQ-5 — RESOLVED → no new proposal kind** (reuse `brief`/`capture`; FR-WD-5 proposes a command) —
  preserves the closed-allow-list floor.
- **OQ-6 — RESOLVED → advance only on a confirmed-OK outcome + a no-progress guard** (Interactive §F
  R2-F9): repeated skip/decline of a step offers friction logging / a different field.

---

*v0.4 — Post-CRP R1 (reviewer claude-opus-4-8[1m], focus-file-steered; 8 F + 7 S, all code-grounded).
**Accept all; none rejected.** Key hardening: completion denominator excludes always-pending
`content`/derived `run` so 100% is reachable (R1-F1) + stage-equal/field-equal weighting (R1-F2) + filled
= present-AND-valid, defaulted-distinct (R1-F7); FR-WD-7 scoped to template-seeded keys with an
`instantiate` precondition since `capture` replaces but can't create a key (R1-F3); discriminating
security acceptance — positive proposal + negative sentinel (R1-F4) + a structural anti-import guard
(plan R1-S1); FR-DC-14 cited (the derive path is already subprocess-contained — R1-F5); re-drive
self-reference guard for the brief (R1-F6); action bound to a `PROPOSAL_KINDS` member (R1-F8); PARTIAL/
retriable outcome→advance mapping (R1-S3). Dispositions in Appendix A; R1 verbatim in Appendix C. Ready
for implementation.*

*v0.3 — Post lessons-learned hardening. Applied 3 SDK design-docs lessons: Leg-1 #5 (vocabulary drift →
ownership split + §Reference-Audit), phantom-reference audit (all symbols verified present), CRP steering
memory (named the CRP target + settled/do-not-relitigate items). No scope pruned — planning already
de-risked the one landmine (FR-WD-5 import→command). Ready for CRP.*

*v0.2 — Post-planning self-reflective update. The headline correction is a **security de-risk**: FR-WD-5
"derive schema from Pydantic models" would have imported untrusted project code (ACE) — reframed to
propose the derive *command* (the human imports their own code). FR-WD-6 simplified onto the existing
`brief` kind; FR-WD-1 reframed as a new `$0` driver loop (not a REPL edit); OQ-3 → union completion model;
OQ-5 → no new proposal kind (security floor intact). Added NR-4a (wizard never imports project code). All
6 OQs resolved. Next: lessons-learned hardening, then CRP.*

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

> Triage R1 (orchestrator, 2026-07-02). **All 8 F + 7 S accepted; none rejected** — grounded in
> `proposals.py`/`capture.py`/`red_carpet.py`/`concierge/derive/` + the closed-allow-list floor.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Exclude content/run from completion denominator (100% reachable) | CRP R1 | FR-WD-2 denominator; plan Step 1 | 2026-07-02 |
| R1-F2 | Define per-stage weighting (stage-equal/field-equal) | CRP R1 | FR-WD-2 weighting; plan Step 1 | 2026-07-02 |
| R1-F3 | `capture` can't create absent key → template-seeded + instantiate precondition | CRP R1 | FR-WD-7; plan Step 3/R1-S4 | 2026-07-02 |
| R1-F4 | Discriminating security test (positive proposal + negative sentinel) | CRP R1 | FR-WD-5 acceptance; plan §7/R1-S5 | 2026-07-02 |
| R1-F5 | Cite FR-DC-14 — derive path already subprocess-contained | CRP R1 | FR-WD-5 framing note | 2026-07-02 |
| R1-F6 | Exclude brief output from re-drive PRD detection | CRP R1 | FR-WD-6 re-drive guard; plan R1-S7 | 2026-07-02 |
| R1-F7 | Present-but-invalid = unfilled; defaulted distinct | CRP R1 | FR-WD-2 filled semantics | 2026-07-02 |
| R1-F8 | Bind found/needed/action to a PROPOSAL_KINDS member | CRP R1 | FR-WD-3 | 2026-07-02 |
| R1-S1 | Structural anti-import guard (AST/grep) test | CRP R1 | plan Step 7 + §7 | 2026-07-02 |
| R1-S2 | Completion denominator/weights in Step 1 | CRP R1 | plan Step 1 | 2026-07-02 |
| R1-S3 | Outcome→advance mapping (PARTIAL/retriable) | CRP R1 | FR-WD-1; plan Step 4/Risk R2 | 2026-07-02 |
| R1-S4 | FR-WD-7 instantiate-first sequencing | CRP R1 | plan Step 3 | 2026-07-02 |
| R1-S5 | Discriminating security proof | CRP R1 | plan §7 | 2026-07-02 |
| R1-S6 | Bucket completion-% attr + emit n_defaulted | CRP R1 | plan Step 6 | 2026-07-02 |
| R1-S7 | Re-drive idempotency case | CRP R1 | plan §7 | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 suggestions were code-grounded and accepted. |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-02

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-02 22:38:19 UTC
- **Scope**: Requirements review weighted to the sponsor focus file — FR-WD-5 no-import stance (residual paths only), the `$0` driver loop, the union completion model, and the reused `brief`/`capture` kinds. Grounded in `kickoff_experience/{proposals,capture,manifest,red_carpet,red_carpet_advisor,readiness,ranking}.py` and `concierge/{core.py,derive/}`.

##### Focus-file asks (answered first; orchestrator triages later)

**Ask 1 — Is FR-WD-5's no-import stance airtight (any residual path where the wizard/inventory/completion imports project code)?**
- **Summary answer:** Yes for the surveyed paths, with one residual gap: the guarantee currently rests on developer discipline, not a structural guard.
- **Rationale:** `build_survey` (`concierge/core.py:112-118`) detects Pydantic models by **reading `.py` text and string-matching `BaseModel`** (`_is_pydantic_module`, core.py:150-155) — a read, never an import. `build_red_carpet_state`'s completion inputs (`_present` file-existence, `build_readiness`, `build_assess`) also never import project modules. The only import/exec path is `introspect_models`→`resolve_models` (`derive/introspect.py:265-276`, `importlib.import_module`), reachable only via `derive-contract`, which the wizard proposes as a command. So no *current* residual path imports project code.
- **Assumptions / conditions:** `wizard_inventory`/`build_completion`/`wizard_prepopulate` (all to-be-created) must never call `build_derivation`/`introspect_models`/`resolve_models`/`importlib`. Nothing structurally prevents a future "be helpful" edit from doing so.
- **Suggested improvements:** Add a structural anti-import guard test (see plan R1-S1) instead of relying only on the behavioral sentinel test. Also note (R1-F5) that even the *proposed* `derive-contract` command is already subprocess-contained (FR-DC-14), so the stance's ACE framing can be made precise without weakening it.

**Ask 2 — Is the `$0` driver loop buildable over `on_proposal`/`apply_proposal`/`render_state` without `ask_sync`, and is auto-advance/no-progress sound?**
- **Summary answer:** Yes, buildable; the advance rule needs one more case (PARTIAL/retriable) to be sound against thrash.
- **Rationale:** `run_red_carpet_repl` (`red_carpet.py:287-324`) is already IO-injected over `pending`/`on_proposal`/`render_state`; a leading loop that reads rank-1 `next_steps` (`build_playbook`, advisor.py:442-520 — steps carry `stage`/`command`) and drives the same seams without `ask_sync` is straightforward. But `apply_proposal` outcomes are not binary: `_RETRIABLE_CODES` includes `STALE_FILE`/`WRITE_BLOCKED`/`PARTIAL` (`proposals.py:48-49`). "Advance only on confirmed-OK" (OQ-6) is underspecified for PARTIAL — see plan R1-S3.
- **Assumptions / conditions:** The driver counts a PARTIAL/retriable outcome as neither "advance" nor "decline-toward-the-no-progress-threshold."
- **Suggested improvements:** FR-WD-1/OQ-6 should enumerate the outcome→advance mapping across `ProposalOutcome.ok`/`.retriable`.

**Ask 3 — Is the union completion model coherent (defaulted counted distinctly, no misleading 100%)?**
- **Summary answer:** Partial — the union is well-motivated but two coherence gaps make the % either never-100 or misleading. See R1-F1, R1-F2.
- **Rationale:** `RedCarpetState` has five stages, of which `content` is hardwired `pending` ("later") and `run` is derived from the gates (`red_carpet.py:150-155`). A denominator over all stages can never reach 100%. And the union equal-weights one structural cascade gate (a whole schema) against one scalar field (e.g. `data_model.datetime`), which misrepresents progress.
- **Assumptions / conditions:** none.
- **Suggested improvements:** R1-F1 (exclude non-fillable stages), R1-F2 (define per-stage weights), and keep the `defaulted`-distinct rule from plan Risk R3.

**Ask 4 — Do the reused `brief`/`capture` kinds accept the pre-populated `source`/values, and does no-clobber behave under re-drive?**
- **Summary answer:** `brief` accepts a `source` string cleanly; `capture` does **not** accept a value for an *absent* field (it edits existing scalars only). No-clobber has a re-drive self-reference hazard.
- **Rationale:** `_apply_brief` (`proposals.py:347-366`) writes `docs/kickoff/REQUIREMENTS.md` from `source` (no-clobber) — FR-WD-6 fits. But `build_capture_plan`→`splice_yaml_value`→`locate_key_line` (`capture.py:90-124,271-340`) raises `KEY_NOT_FOUND` when the dotted key is absent and `TARGET_FILE_MISSING` when the domain file is absent — capture **replaces**, it cannot **create** a key. FR-WD-7's "absent value-input field" therefore fails at apply unless the template already seeds the key. Separately, `build_survey` globs `**/*REQUIREMENTS*.md` (core.py:37), which will list the brief output on re-drive (R1-F6).
- **Assumptions / conditions:** Instantiate has scaffolded the inputs package and the templates seed each writable field's key with a placeholder scalar.
- **Suggested improvements:** R1-F3 (scope FR-WD-7 to template-seeded keys + state the instantiate precondition), R1-F6 (exclude the brief output from re-drive PRD detection).

##### Executive summary

- **Completion % can never reach 100** if the always-pending `content` stage (and derived `run`) are in the denominator — contradicts FR-WD-2's "you're X% done" (R1-F1).
- **Union weighting is undefined** — a cascade gate equal-weighted with a scalar field misrepresents progress (R1-F2).
- **FR-WD-7 collides with `capture` semantics** — capture cannot create an absent key; "pre-fill absent field" fails at apply without a template-seeded key (R1-F3).
- **FR-WD-5 acceptance test is vacuously passable** — a wizard that errors early also "never triggers the sentinel" (R1-F4).
- **ACE framing overstates the existing derive path** — `derive-contract` is already subprocess-contained/fail-closed (FR-DC-14); cite it so the stance is precise (R1-F5).
- **Re-drive self-reference** — survey re-detects the just-written brief as a PRD, risking a would_clobber loop (R1-F6).
- No-import stance is otherwise airtight; the driver loop is buildable over the existing seams.

##### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Define the FR-WD-2 completion **denominator** as user-fillable units only — `{cascade gates} ∪ {writable value-input fields}` — and explicitly exclude the `content` (always-pending "later") and `run` (derived) stages from the % so a fully-filled project reads 100%. | `red_carpet.py:150-155` hardwires `content` to `pending` and derives `run` from the gates; including them makes overall % structurally never-100, contradicting "surfaced by the driver ... you're 60% done." | FR-WD-2 (after "plus the cascade gates") | Fixture with all four gates + all writable fields present → `build_completion` overall == 100%. |
| R1-F2 | Data | high | Specify the **per-stage weighting** of the union so overall % is not dominated by the 10 scalar fields vs the 4 structural gates (or vice-versa). State the formula (e.g., stage-equal then field-equal within stage). | FR-WD-2 says "weighted per stage" but no weights are given; equal-weighting a whole-schema gate with `data_model.datetime` misrepresents progress and enables the R3 "gaming/confusion." | FR-WD-2 | Hand-counted fixture across stages matches the documented weight formula (plan §7 "Completion correctness"). |
| R1-F3 | Interfaces | high | Scope FR-WD-7 to fields whose **keys the input templates already seed** post-`instantiate`, and state the precondition. Note capture **replaces** a scalar; it cannot create an absent key. | `build_capture_plan`/`splice_yaml_value` raise `KEY_NOT_FOUND` for an absent dotted key and `TARGET_FILE_MISSING` for an absent domain file (`capture.py:163-165,316-321`). "For each absent value-input field ... a `capture` proposal pre-filling it" fails at apply otherwise. | FR-WD-7 | Capture proposal for a field-key absent from the template returns `KEY_NOT_FOUND` (documented, typed, not a crash); pre-fill of a seeded key succeeds. |
| R1-F4 | Validation | high | Make the FR-WD-5 acceptance test **discriminating**: assert the wizard **did** survey the model file **and did** emit the derive-command proposal naming it, *and* the import-time sentinel is untouched. | As written ("a fixture model with an import-time side effect is never triggered by running the wizard"), a wizard that errors early or never targets the model passes vacuously — proving nothing about the no-import property. | FR-WD-5 → Acceptance bullet | Test asserts both the positive (proposal emitted, model file named) and the negative (sentinel file absent). |
| R1-F5 | Security | medium | In §0 / FR-WD-5, cite **FR-DC-14 containment** — the proposed `derive-contract` runs introspection in a scrubbed-env, timeout-bounded, **fail-closed subprocess** (`concierge/derive/containment.py`, `_introspect_subproc.py`), not a raw in-process import. Keeps the stance; corrects the ACE framing. | The docs imply "importing untrusted project code = ACE" flatly; the *existing* derive path already contains that ACE. Precise framing prevents a future reviewer concluding the whole derive feature is unsafe. | §0 planning table (FR-WD-5 row) + FR-WD-5 body | Reviewer confirms the cited modules subprocess-isolate `introspect_models`. |
| R1-F6 | Data | medium | FR-WD-6 must **exclude the brief output** (`docs/kickoff/REQUIREMENTS.md`) from re-drive PRD detection, and skip the proposal when the brief gate is already met, so the driver does not re-propose a brief from the file it just wrote. | `build_survey` globs `**/*REQUIREMENTS*.md` (`core.py:37`); after a confirmed brief, re-drive re-lists that file as a PRD candidate → `_apply_brief` `would_clobber` loop / self-reference. | FR-WD-6 (add a re-drive/no-clobber clause) | Re-drive after a confirmed brief emits **no** new `brief` proposal; survey/inventory omits the brief path. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F7 | Risks | medium | FR-WD-2/FR-WD-9: define how a field that is **present-but-invalid** (a hand-edit that fails the round-trip / an `input-invalid` advisory) counts in the meter — "filled" must not mask an invalid value that still blocks the cascade. | `readiness` emits `input-invalid` advisories and `capture` gates on round-trip (`capture.py:209-230`); a naive "filled = key present" would show progress while the build is blocked, contradicting P3 resumable/brownfield. | FR-WD-2 (filled semantics) + FR-WD-9 | Fixture with a malformed inputs value → completion reports it as invalid/unfilled, not filled. |
| R1-F8 | Interfaces | low | FR-WD-3's found/needed/action triple should name **which proposal kind** the "action" maps to (`brief`/`capture`/command) so the contract is testable against the closed `PROPOSAL_KINDS` allow-list, not free prose. | FR-WD-3 says "a proposal to confirm, or a command" but does not bind the action to a kind; binding keeps it deterministic and lets a test assert the kind is in `PROPOSAL_KINDS`. | FR-WD-3 | Snapshot test: each step's action kind ∈ `PROPOSAL_KINDS` ∪ {command}. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round.
