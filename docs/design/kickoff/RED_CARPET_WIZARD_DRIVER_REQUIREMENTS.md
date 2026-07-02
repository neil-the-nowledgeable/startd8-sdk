# Red Carpet Wizard-Driver + Asset-Chaining — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
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
  states "found / gap / do this", offers the pre-populated proposal(s), and **advances on a confirmed-OK
  outcome**. It does **not** modify `run_red_carpet_repl` (which stays as the agentic fallback, FR-WD-8).
  CLI: `startd8 kickoff red-carpet --wizard`. The step/completion model is surface-neutral (web later).
- **FR-WD-2 — Completion meter.** Add a real **filled/total completion model** over the input surface:
  per-stage progress + an overall percentage derived from `default_config().writable_fields()` (value
  inputs) plus the cascade gates (schema/app/pages/views). Attached to `RedCarpetState` (additive),
  surfaced by the driver and `--json`. Distinct from the coarse `readiness_score`.
- **FR-WD-3 — Step presentation contract.** For each step the driver renders a structured
  **found / needed / action** triple: what the pre-populate pass already derived (with provenance), what
  is still missing, and the exact next action (a proposal to confirm, or a command). Deterministic and
  testable.

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
  - **Acceptance:** a fixture model with an import-time side effect is **never triggered** by running the
    wizard (the wizard proposes the command; it does not import). Verify with a sentinel-on-import fixture.
- **FR-WD-6 — Propose a brief from an existing PRD** *(simplified by planning)*. When `survey` finds a
  requirements/PRD doc and no confirmed brief, the driver **proposes a `brief` action whose `source` is the
  PRD's content** (read-only, `$0`, safe — the existing `brief` kind writes `docs/kickoff/REQUIREMENTS.md`,
  no-clobber), so the user confirms/edits rather than starting from a blank interview. No new extraction.
- **FR-WD-7 — Pre-fill value-input fields.** For value-input steps, the driver **proposes** field values
  pre-filled from any existing `inputs/*.yaml` + the seeded `default_config` provenance defaults, so the
  user confirms/edits rather than authors from scratch (rides `capture.build_capture_plan`; each field a
  confirmable proposal).
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
