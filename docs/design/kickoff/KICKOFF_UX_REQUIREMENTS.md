# Kickoff UX / Information Architecture — Requirements

**Version:** 0.4 (Post-CRP R1)
**Date:** 2026-07-02
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `KICKOFF_UX_PLAN.md`
**Governs the presentation of (cite, don't re-spec the mechanisms):**
`RED_CARPET_TREATMENT_REQUIREMENTS.md` (the conductor + P5 gap-loop), `RED_CARPET_PRESCRIPTIVE_ADVISOR_REQUIREMENTS.md`
(advisories + `next_steps` playbook), `RED_CARPET_WIZARD_DRIVER_REQUIREMENTS.md` (the driver + completion
model), `INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (field states / guided next-step / readiness).

> **What this is.** The kickoff experience grew feature-by-feature (conductor → advisor → wizard-driver),
> each appending its own block to the CLI, with **no UX/IA requirements to hold it together**. The result
> is a ~40-line wall of redundant, jargon-heavy output that confuses even the SDK's own author. This spec
> **owns the presentation layer** — the mental model, the plain-language vocabulary, progressive
> disclosure, the progress spine, and the wizard step contract — so every surface presents the *same*
> mechanisms coherently. It changes **no backend behavior**; it governs how what already exists is shown.

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass made this **smaller and more concrete**: the "four things" mental model is not a new
> structure to invent — it maps **1:1 onto the existing 5 stages**, plain-renamed. The spec collapses to
> "one presentation module (glossary + spine + headline) + a `--verbose` flag + render swaps," changing
> **no** mechanism.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The four-things model is a new structure to design | It is the **existing 5 `STAGES` renamed** (`data_model`→data, `manifests`→screens, `value_inputs`→settings, `content`→placeholder, `run`→Build). | **FR-UX-1/6 simplify:** rename, don't restructure. The spine is the stages rendered **once**. |
| A glossary might exist (OQ-1) | **None exists** in `kickoff_experience/`. | **OQ-1 → net-new** single-source `GLOSSARY` in a new `presentation.py`. |
| `--verbose` exists (OQ-3) | It does **not** — `red-carpet` has `--json`/`--check`/`--wizard`/`--agent`. | **OQ-3 → add `--verbose`.** |
| Headline action from `ranking.next_action` (OQ-4) | `next_action` reads jargon ("Resolve readiness blocker: Services"); the **playbook rank-1** reads "Author the data-model contract". | **OQ-4 → use `next_steps[0]`**, glossary-translated. |
| Both %s matter (OQ-5) | `completion.overall_pct` = "how done"; `readiness_score` = coarse. | **OQ-5 → headline = completion %.** |
| Greenfield-calm needs advisory-data change (OQ-6) | Derivable at render (overall_pct==0 + schema absent); cascade-blockers are already `warn`, just dominant. | **OQ-6 → presentation-only** (move blockers to `--verbose`). |
| The wizard wall needs a driver change (FR-UX-9) | The **CLI wrapper** passes `_render_red_carpet_state` (full wall) as the driver's per-step render. | **FR-UX-9 → swap the render callback** — no driver change. |

**Resolved open questions:** OQ-1 → net-new `GLOSSARY` in `presentation.py`. OQ-2 → spine derivable from
`stages`/`next_stage`/`completion` (no new state). OQ-3 → add `--verbose`. OQ-4 → headline action =
`next_steps[0]` translated. OQ-5 → headline = `completion.overall_pct`. OQ-6 → presentation-only calm.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons before CRP:

- **[Leg-1 #5 — Vocabulary drift / single-source ownership]** — *directly on point:* this spec's whole
  job is a plain-language vocabulary. Fix: the `GLOSSARY` (FR-UX-2) is declared the **single owner** of
  every user-facing name; no surface hardcodes a plain name, and a **no-jargon test** (plan §6) enforces
  it. This doc **owns** the presentation/IA vocabulary; the cited specs own the mechanisms and are
  non-normative snapshots here.
- **[Phantom-reference audit]** — every code symbol named was grepped and exists (see §Reference-Audit);
  the new symbols are marked to-be-created.
- **[CRP steering memory]** — this is a **brand-new** doc (least-reviewed) → the CRP target. Settled /
  do-not-relitigate (carried to the focus file): **presentation-only, no mechanism change** (NR-1/2), the
  `--json` stability (NR-3), and RCT P5 (gap-loop, not a fixed wizard — the spine is a *view*, not a
  forced sequence).

### Reference-Audit

| Symbol | Owning module (verified present) |
|--------|----------------------------------|
| `build_red_carpet_state` / `RedCarpetState.stages`/`.next_stage`/`.completion` / `STAGES` | `kickoff_experience/red_carpet.py` |
| `next_steps` / `build_playbook` (rank-1 "Author the data-model contract") | `kickoff_experience/red_carpet_advisor.py` |
| `completion.overall_pct` | `kickoff_experience/red_carpet_completion.py` |
| `_render_red_carpet_state` / `red_carpet_cmd` / `_run_red_carpet_wizard` | `cli_kickoff.py` |
| `run_red_carpet_driver` (renders one step; wrapper passes the full-wall render) | `kickoff_experience/wizard.py` |

*New symbols this doc introduces (to-be-created): `presentation.py`, `GLOSSARY`, `build_spine`,
`headline`, `render_wizard_step`.* Confirmed absent today: no `--verbose` flag, no glossary.

---

## 1. Problem Statement

Running `startd8 kickoff red-carpet` (and `--wizard`) today produces this (abridged, real output):

```
🟥 Red Carpet — readiness 33% · 0% complete
  data_model 0/1 · manifests 0/3 · value_inputs 0/8
  … data_model (next) — interview → derive + promote the data-model contract (the front bookend)
  … manifests — author the assembly manifests (pages/views/app/…) from the schema
  … value_inputs — scaffold the kickoff package (propose `instantiate`), …
  … content — placeholder content + static test data (later)
  … run — cascade not offerable — unmet: schema, app, pages, views
Insights
  • Cascade blocker: Content Inputs (buckets 2/4 — visibility only) — …
  • Cascade blocker: Pages & Nav — …            startd8 kickoff red-carpet --agent
  • Cascade blocker: Services — no contract → …
  • Value input missing: build-preferences — … Fields to fill: build_per_run, build_profile.
  • Value input missing: business-targets — …
  • Value input missing: conventions — …
  • No data model yet — …                        startd8 kickoff red-carpet --agent
Next steps
  1. Author the data-model contract              startd8 kickoff red-carpet --agent
  2. Add app manifest                            startd8 kickoff red-carpet --agent
  … 7 total, each the same command …
Cascade not offerable yet — unmet gates: schema, app, pages, views.
```

| Problem (observed) | Why it confuses | What good looks like |
|--------------------|-----------------|----------------------|
| **Information overload** — ~40 lines at once | No focus; the user can't tell what to *do* | A focused summary + **one** next action; details on demand |
| **3× redundancy** — the same gap in stages, Insights, AND Next steps | Feels like three different problems; it's one | One concept, shown once |
| **Two unexplained %s** — `readiness 33% · 0% complete` | Which matters? What's the difference? | One headline number; the other explained or hidden |
| **Insider jargon** — cascade, manifests, value_inputs, "front bookend", "buckets 2/4" | The author is confused; end users have no chance | Plain language, owned by one glossary |
| **`--wizard` front-loads the whole wall** then prompts | It doesn't feel *led*; it feels dumped-on | One step at a time |
| **Alarming greenfield noise** — 3 red "Cascade blocker"s | A blank project reads as broken | "You haven't started — begin with your data" |

**Root cause:** the kickoff has real UX debt because it has **no UX requirements**. Each feature was
technically correct and independently reviewed, but nothing governed how they *compose* on screen.

**What should exist:** a small, durable **UX/IA spec** that defines the user's mental model, the
plain-language vocabulary, the disclosure rules, one progress spine, and the wizard step contract — so
the CLI (and later the web surface) present the existing mechanisms coherently and calmly.

---

## 2. Guiding Principles

- **UX-P1 — One thing at a time.** Every surface has a single focal point: the status view shows *where
  you are + the one next action*; the wizard shows *one step*. Depth is available, never forced
  (progressive disclosure).
- **UX-P2 — Plain language is the default; jargon is opt-in.** The primary surface speaks the user's
  words ("Your data", "Your screens", "Build"). Internal vocabulary (`cascade`, `manifest`, `value_path`)
  appears only under `--verbose`/`--json` or in docs.
- **UX-P3 — Say each thing once.** A gap is one concept. It appears in exactly one place per surface; the
  stage map, the advisories, and the playbook are *views of the same state*, not three lists.
- **UX-P4 — Calm, not alarming.** A blank project is normal, not broken. Severity/color reflects real
  user urgency, not internal machinery state.
- **UX-P5 — This spec owns presentation; it never changes mechanism.** No new backend behavior, grammar,
  or write path. It re-shapes what `build_red_carpet_state`/the advisor/the wizard already produce.

---

## 3. Requirements

### A. The mental model & vocabulary (surface-neutral)

- **FR-UX-1 — The mental model: three things to provide + Build** *(corrected by CRP R1-F1)*. The kickoff
  is presented as **three things the user provides**, plain-named, in dependency order, then **Build** as
  the destination — **plus** an *optional* add-on:
  1. **Your data** — the things your app stores (→ the schema).
  2. **Your screens** — the pages & views built from your data.
  3. **Your settings** — a few choices (language, money format, budget…) — *small, mostly defaults*.
  Then **Build** — the `$0` generate step. **Build never renders as a completed "✓ done" thing:** the
  underlying `run` stage becomes `"done"` when merely **offerable, not built** (`red_carpet.py`), so the
  spine must use a distinct terminal status (e.g. `ready`) so ✓ is never shown for a never-generated app.
  **Placeholder content** is an **optional add-on**, *not* an equal fourth item — it is always-pending and
  excluded from completion; it renders de-emphasized, like the FR-UX-3 right-sizing of settings.
- **FR-UX-2 — A single plain-language glossary (owned here), applied to free text too** *(hardened, CRP
  R1-F2)*. One `GLOSSARY` is the **single source** for user-facing names: `data_model`→"Your data",
  `manifests`→"Your screens", `value_inputs`→"Your settings", `cascade`→"Build", `content`→"Placeholder
  content". But jargon also leaks through **free text the render passes verbatim** — advisory/playbook
  `detail`/`action` ("the front bookend…", "@relation", "prisma/schema.prisma", "CRUD"), the wizard
  found/needed strings, and the per-stage **completion meter** which today prints raw keys
  (`data_model 0/1`). So: **any user-facing string derived from advisory/playbook/wizard text is
  glossary-translated**, not just the stage names; and the no-jargon test (a) also scans `--verbose`
  output and any `next_steps[0]` text the headline consumes, and (b) uses an expanded token list —
  `{cascade, manifest, value_path, prisma, schema, @relation, @@id, provenance, gate, bookend, buckets}`.
  Internal names remain only in `--json`.
- **FR-UX-3 — Right-size the "settings" bucket (with a render rule).** *Settings* is small (≈8 fields,
  mostly dropdowns with sane defaults) and not equal-weight with data/screens. **Acceptance (CRP R1-F5):**
  it renders as **a single collapsed line** (name + field count, e.g. "Your settings · 2 of 8"), visually
  **subordinate** to data/screens — testable via a snapshot, not just asserted.

### B. The status view (`startd8 kickoff red-carpet`, read-only)

- **FR-UX-4 — Focused summary + one next action.** The default status view shows: a one-line progress
  header (spine + one headline %), the four-things map with a clear "**you are here**", and **the single
  highest-value next action** (plain language + its command). Nothing else by default.
- **FR-UX-5 — Progressive disclosure — but never hide errors** *(hardened, CRP R1-F4)*. The full advisory
  list and the ranked playbook move behind `--verbose`; the machine payload stays on `--json` (unchanged).
  **Exception:** `severity == "error"` advisories (invalid input YAML, unresolved assembly inputs — the
  exact set `--check` exits 1 on) are **NOT hidden** — the default view surfaces at least a count/banner
  ("⚠ 1 problem needs fixing → `--verbose`"), so the human view and CI (`--check`) never disagree. (The
  "one next action" is dependency-ordered, so an error below an unmet gate would otherwise surface
  nowhere.) The default view ends with a one-line "N more details → `--verbose`" pointer.
- **FR-UX-6 — One progress spine, no triple redundancy (UX-P3).** The stage map, advisories, and playbook
  are rendered as **one** progress spine (the four things + Build, each with a compact status), not three
  parallel lists. A gap is named once.
- **FR-UX-7 — Reconcile the two percentages; be honest about "filled ≠ buildable"** *(hardened, CRP
  R1-F3)*. Exactly **one** headline number is shown by default — the user-fillable **completion %**
  (FR-WD-2). But `overall_pct` is **presence-based, not validity-based** (`_present` = file exists & size
  > 0, not parse-valid), and counts `defaulted` values as filled — so it can read **100%** for an
  unbuildable project. FR-UX-7 defines the headline as **"% filled," not "buildable,"** and requires it to
  **annotate the gap**: "100% filled · not yet buildable" when an error advisory / unmet gate persists, and
  "· N defaulted — review" when filled units are all defaulted. `readiness_score` → `--verbose` (labeled).
- **FR-UX-8 — Calm greenfield (UX-P4) — but not by suppressing errors** *(scoped, CRP R1-F4)*. A blank
  project reads "not started — begin with **Your data**", not red "Cascade blocker" noise (those are
  dependency-fanout `warn`s → `--verbose`). "Calm" applies to **greenfield / warn-level** state only; it
  **never** suppresses `error`-severity advisories (FR-UX-5 exception).

### C. The wizard (`--wizard`)

- **FR-UX-9 — One step at a time (no status wall).** The wizard does **not** print the full status view.
  It opens with a one-line framing, then renders **one step**: a compact spine (Step N of M · plain name),
  the **found / needed / action** triple in plain language, and the confirm prompt. On advance, the next
  step — never the whole wall. **Correction (CRP R1-S1):** the compact renderer consumes the driver's
  `state` (the driver calls `render_state(state)` *before* the step action exists), not `(action, spine)`.
- **FR-UX-10 — Plain-language step copy** *(scope corrected — not a pure render swap, CRP R1-S2)*. The
  wizard's found/needed/action uses the glossary. **Planning error corrected:** the found/needed lines are
  emitted by the **driver** (`run_red_carpet_driver`) with raw stage keys, so plain copy is achieved by
  **glossary-translating `found`/`needed` at `WizardAction` construction in `wizard.py`** (still
  presentation-only — the wizard module, no proposal/behavior change), *not* by swapping the render
  callback alone. (§0's "no driver change" claim was too strong; the change stays inside the wizard
  module's presentation surface.)
- **FR-UX-11 — Status vs wizard split (clear roles).** `red-carpet` (no flag) = **glance** (where am I,
  what's next); `--wizard` = **do** (guided, step-by-step); `--agent` = **talk** (LLM interview);
  `--json`/`--verbose` = **detail/scripting**. Each mode's purpose is stated in help and honored in output.

### D. Cross-surface

- **FR-UX-12 — Surface-neutral IA reused by the web.** The mental model (FR-UX-1), glossary (FR-UX-2), the
  spine + "you are here", and the step contract (FR-UX-9) are defined independent of the terminal, so the
  web `/concierge/chat` rail renders the *same* four-things spine, plain names, and one-step wizard. (The
  web build is a later increment; this spec makes it fall out of the same model.)

---

## 4. Non-Requirements

- **NR-1 — No new backend feature / grammar / write path.** Presentation only; `build_red_carpet_state`,
  the advisor, the completion model, and the wizard proposals are unchanged in behavior.
- **NR-2 — No change to what the cascade builds** or to the offer predicate / gates.
- **NR-3 — `--json` shape is stable.** Machine consumers are untouched (additive only, if anything).
- **NR-4 — Not a visual/web build.** The web wizard is a later increment; this spec only makes the IA
  reusable by it.
- **NR-5 — Not new content.** It renames/organizes existing copy; it doesn't author real user content.

---

## 5. Open Questions

*All 6 resolved by the planning pass — see §0.*

- **OQ-1 — RESOLVED → net-new single-source `GLOSSARY`** in a new `presentation.py` (none exists today).
- **OQ-2 — RESOLVED → spine derivable** from `stages`/`next_stage`/`completion` via a small presentation
  helper; no new state.
- **OQ-3 — RESOLVED → add `--verbose`** (no such flag today).
- **OQ-4 — RESOLVED → headline action = `next_steps[0]`** (playbook rank-1, glossary-translated) — plainer
  than `ranking.next_action`'s "Resolve readiness blocker: …".
- **OQ-5 — RESOLVED → headline = `completion.overall_pct`;** readiness → `--verbose` (labeled).
- **OQ-6 — RESOLVED → presentation-only calm** (greenfield detected at render via `overall_pct==0` +
  schema absent; cascade-blocker advisories move behind `--verbose`; no advisory-data change).

---

*v0.2 — Post-planning self-reflective update. The loop **shrank and de-risked** the spec: the four-things
model is the existing 5 stages **renamed** (not restructured), so the whole thing collapses to one new
`presentation.py` (glossary + spine + headline) + a `--verbose` flag + two render swaps — **zero mechanism
change**. All 6 OQs resolved. Next: lessons-learned hardening, then CRP.*

*v0.4 — Post-CRP R1 (reviewer claude-opus-4-8-1m, focus-steered; 6 F + 6 S, all code-grounded).
**Accept all; none rejected.** Material corrections: Build never renders "✓ done" (offerable ≠ built) +
content demoted to an optional add-on (R1-F1); the glossary applies to **free text** (advisory/playbook/
wizard/meter), and the no-jargon test scans `--verbose` + `next_steps[0]` with an expanded token list —
non-gameable (R1-F2); `overall_pct` = "% filled" not "buildable", headline annotates not-yet-buildable /
all-defaulted (R1-F3); `--verbose` **never hides `error`-severity advisories** — default shows an error
banner, reconciling with `--check` (R1-F4); FR-UX-3 settings right-sizing gets a concrete render rule +
snapshot (R1-F5); and the biggest — **"no driver change" was false:** the wizard found/needed jargon is
emitted by the driver, so plain copy is done at `WizardAction` construction (still presentation-only), and
`render_wizard_step` consumes `state` not `(action,spine)` (R1-S1/S2). Version pointers synced (R1-F6/S6).
Dispositions in Appendix A; R1 verbatim in Appendix C. Ready for implementation.*

*v0.3 — Post lessons-learned hardening. Applied 3 SDK design-docs lessons: Leg-1 #5 (single-source
`GLOSSARY` ownership + no-jargon enforcement — directly on point for a vocabulary spec), phantom-reference
audit (all symbols verified; new ones marked to-be-created), CRP steering (named the target + settled
items). No scope pruned. Ready for CRP.*

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

> Triage R1 (orchestrator, 2026-07-02). **All 6 F + 6 S accepted; none rejected** — grounded in
> `red_carpet*.py`/`wizard.py`/`cli_kickoff.py`.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-F1 | Build never "✓done" (offerable≠built); content = optional add-on | CRP R1 | FR-UX-1; plan Step 1 (spine terminal `ready`) | 2026-07-02 |
| R1-F2 | Glossary applies to free text; no-jargon test non-gameable | CRP R1 | FR-UX-2; plan Step 2/6 (expanded tokens, --verbose scan) | 2026-07-02 |
| R1-F3 | overall_pct = "% filled" not "buildable"; annotate | CRP R1 | FR-UX-7; plan Step 1 | 2026-07-02 |
| R1-F4 | --verbose never hides error advisories; default banner | CRP R1 | FR-UX-5/8; plan Step 2/R1-S4 | 2026-07-02 |
| R1-F5 | FR-UX-3 settings right-sizing render rule + snapshot | CRP R1 | FR-UX-3; plan Step 2/R1-S5 | 2026-07-02 |
| R1-F6 | Sync version pointers | CRP R1 | plan header → reqs v0.4 | 2026-07-02 |
| R1-S1 | render_wizard_step consumes `state`, not `(action,spine)` | CRP R1 | plan Step 3; FR-UX-9 | 2026-07-02 |
| R1-S2 | "no driver change" false — translate at WizardAction | CRP R1 | plan Step 3 + discovery row; FR-UX-10 | 2026-07-02 |
| R1-S3 | Glossary-translate the completion meter (raw keys today) | CRP R1 | plan Step 2 | 2026-07-02 |
| R1-S4 | Error advisories stay in default (banner) | CRP R1 | plan Step 2 + Risk R1 | 2026-07-02 |
| R1-S5 | Operationalize FR-UX-3 (plan step + test) | CRP R1 | plan Step 2/6 | 2026-07-02 |
| R1-S6 | Sync plan front-matter to reqs v0.4 | CRP R1 | plan header | 2026-07-02 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 suggestions were code-grounded and accepted. |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-02

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-02 23:45:00 UTC
- **Scope**: Presentation/IA spec review, weighted per the sponsor focus file (mental-model→stages mapping, single glossary + no-jargon guard, progressive disclosure vs hiding, headline honesty, wizard render swap). Grounded in `kickoff_experience/{red_carpet,red_carpet_advisor,red_carpet_completion,wizard,ranking}.py` and `cli_kickoff.py`.

##### Sponsor focus asks (answered first)

**Ask 1 — Is "four things + Build = the 5 stages renamed" clean, or does a stage carry two meanings?**
- **Summary answer:** Mostly clean, but **`run`→"Build" carries two meanings** and `content` is a false peer.
- **Rationale:** In `red_carpet.py:154-158` the `run` stage status becomes `"done"` when `cascade_offerable` is true — i.e. **offerable, not built**. `build_spine` derives node status from `state.stages` (Plan Step 1), so a project that has never generated anything would render **Build ✓ done**, which reads as "already built." Separately, `content` is hardcoded `"pending"` forever (`red_carpet.py:153`) and is **excluded from `build_completion`** (`red_carpet_completion.py:92-115` counts only data_model/manifests/value_inputs), so presenting "Placeholder content" as one of the *four things the user provides* (FR-UX-1) overstates it — it is a no-op stage, unlike `settings` which FR-UX-3 explicitly right-sizes.
- **Assumptions / conditions:** `build_spine` maps `run.status=="done"` to a ✓/done glyph.
- **Suggested improvements:** In FR-UX-1, state that **Build is a destination that never renders as "done"** — use a distinct terminal status (e.g. `ready`/`built`) so ✓ is never shown for merely-offerable; and mark `content` as an *optional add-on*, not an equal fourth "thing" (parallel to the FR-UX-3 right-sizing of settings). See R1-F1.

**Ask 2 — Is one `GLOSSARY` sufficient, and is the no-jargon test a real guard or gameable?**
- **Summary answer:** One glossary is necessary but **not sufficient**, and the no-jargon test as specified is **gameable**.
- **Rationale:** The glossary only renames the 5 stage keys. Jargon lives in *free-text* the render passes through verbatim: advisory `detail`/`action` ("the front bookend everything derives from", `red_carpet_advisor.py:179`; "@relation", "@@id", "CRUD + findUnique", "prisma/schema.prisma"), the playbook rank-1 detail "promote prisma/schema.prisma (the front bookend)" (`red_carpet_advisor.py:460` — the very `next_steps[0]` FR-UX-4 feeds the headline), and the wizard's `found/needed` strings (`wizard.py:104,128`). Because FR-UX-5/8 move advisories behind `--verbose`, a no-jargon test that scans only the **default** view (Plan §6/Step 6) **passes trivially by hiding, not translating** — and its token set `{cascade, manifest, value_path, front bookend, buckets}` misses `schema`, `prisma`, `@relation`, `@@id`, `provenance`, `gate`, `bookend` (only the bigram "front bookend" is listed).
- **Assumptions / conditions:** advisory/playbook `detail` text is rendered unmodified (it is today).
- **Suggested improvements:** Require the no-jargon guard to also run over `--verbose` output and over `next_steps[0].detail`/`.command` whenever the headline consumes them; expand the token list; add a rule that any user-facing string derived from advisory/playbook text is glossary-translated, not just the stage names. See R1-F2.

**Ask 3 — Does moving advisories/cascade-blockers behind `--verbose` ever hide something the user must see?**
- **Summary answer:** **Yes** — it hides **error-severity** advisories.
- **Rationale:** `KIND_INPUT_INVALID` and "Assembly inputs did not resolve" are `SEVERITY_ERROR` (`red_carpet_advisor.py:293,354`) — the exact set `--check` exits 1 on (`cli_kickoff.py:359`). FR-UX-5 ("full advisory list → `--verbose`") and FR-UX-8 (cascade-blockers → `--verbose`) would make the human default view read *calm* while CI is *red*. Worse, the "one next action" is `next_steps[0]`, which is **dependency-ordered** (schema→app→pages→views, `build_playbook:457-467`), not severity-ordered — so an invalid `conventions.yaml` is ranked below any unmet gate and, being an advisory, is also hidden. It surfaces **nowhere** by default.
- **Assumptions / conditions:** a project can have an error advisory while an earlier gate is unmet.
- **Suggested improvements:** Carve `severity == "error"` advisories out of the `--verbose` hide rule: the default view must show at least a count/banner ("⚠ 1 problem needs fixing → `--verbose`"), reconciling the human view with `--check`. See R1-F4 / plan R1-S4.

**Ask 4 — Is `completion.overall_pct` always the honest "how done" number?**
- **Summary answer:** **No** — it can read 100% for an unbuildable project.
- **Rationale:** `data_model` completion keys off `"schema" in unmet` (`red_carpet_completion.py:92`), and `unmet` is `_present` = *file exists & size>0* (`red_carpet.py:83-88`), **not parse validity**. A present-but-unparseable `schema.prisma` + all manifests + all fields present ⇒ `overall_pct == 100` while the advisor emits "Schema not parseable" and the real cascade gate may reject it — exactly the focus's "all fields filled but schema invalid" case. Also `build_completion:110-112` counts **defaulted** values as filled, so "100% complete (8 defaulted — review)" reads done when nothing was user-confirmed.
- **Assumptions / conditions:** none — both paths are reachable today.
- **Suggested improvements:** FR-UX-7 should define overall_pct as "% filled," **not** "buildable," and require the headline to annotate the gap ("100% filled · not yet buildable" when errors/unmet gates persist, or when `n_defaulted == filled`). See R1-F3.

**Ask 5 — Does the wizard render swap lose signal needed for the per-step confirm?**
- **Summary answer:** The *local* confirm signal survives, but the swap as specified is **not wireable** and **cannot deliver FR-UX-10** without a driver change.
- **Rationale:** `run_red_carpet_driver` calls `render_state(state)` (`wizard.py:194`) **before** it computes the step action (`wizard.py:198`), and the found/needed/action lines are emitted by the **driver itself** via `emit_line` (`wizard.py:210-213`) using raw stage keys — not by the swappable `render_state`. So (a) Plan Step 3's `render_wizard_step(action, spine)` cannot be passed as the `render_state(state)` callback (arg mismatch), and (b) glossary-translated step copy (FR-UX-10) requires touching the driver's emit lines — contradicting the "swap the render callback, no driver change" premise (§0 / FR-UX-9). The confirm decision itself reads `action.summary()` in `_on_proposal` (`cli_kickoff.py:288`), which the swap does not touch, so the local decision is safe.
- **Assumptions / conditions:** the found/needed emit lines stay in the driver.
- **Suggested improvements:** Either translate `found`/`needed` at `WizardAction` construction (in `wizard.py`, still presentation-only) or acknowledge a small driver change; fix the `render_wizard_step` signature to consume `state`. See plan R1-S1 / R1-S2.

##### Feature Requirements Suggestions (first pass)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Interfaces | high | In FR-UX-1, specify that **Build never renders as a completed "thing"** (use a terminal `ready`/`built` status distinct from ✓done) and demote **Placeholder content** to an optional add-on, not an equal fourth item. | `run.status=="done"` means *offerable* not *built* (`red_carpet.py:154-158`); `content` is always `pending` and excluded from completion (`red_carpet_completion.py:92-115`), so a spine deriving status from `state.stages` mis-signals both. | FR-UX-1 (the four-things list + "Plus Build") | Snapshot: an offerable-but-never-generated project shows Build as "ready", not ✓; content is visually de-emphasized. |
| R1-F2 | Validation | high | Make FR-UX-2's no-jargon test non-gameable: run it over `--verbose` output and over any `next_steps[0]` text the headline consumes, expand the token list (`schema`, `prisma`, `@relation`, `@@id`, `provenance`, `gate`, `bookend`), and require advisory/playbook `detail`/`action` to be glossary-translated — not just stage names. | Jargon leaks via passed-through free text (`red_carpet_advisor.py:179,460`); hiding advisories behind `--verbose` lets a default-only test pass without translating (Plan §6). | FR-UX-2 + a new acceptance clause | A jargon token planted in an advisory `detail` fails the test even when advisories are behind `--verbose`. |
| R1-F3 | Data | high | FR-UX-7 must state overall_pct = "% of fillable units present," **not** "buildable," and require the headline to flag (a) present-but-invalid schema and (b) all-defaulted completion. | `overall_pct` keys off `_present` (size>0), not validity (`red_carpet_completion.py:92` / `red_carpet.py:83-88`); defaulted values count as filled (`:110-112`) → 100% can mislead. | FR-UX-7 | Unit: a present-unparseable schema (or all-defaulted inputs) yields a headline that is not an unqualified "100% complete". |
| R1-F4 | Risks | high | FR-UX-5/FR-UX-8 must exempt `severity=="error"` advisories from the `--verbose` hide rule; the default view surfaces at least an error count/banner. | Error advisories (`INPUT_INVALID`, inputs-not-resolved) are what `--check` fails on (`red_carpet_advisor.py:293,354`; `cli_kickoff.py:359`); hiding them makes the human view disagree with CI, and dependency-ordered `next_steps[0]` won't surface them either. | FR-UX-5 and FR-UX-8 | Test: a project with one invalid input shows a non-hidden "1 problem" signal by default; `--check` and default view agree. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F5 | Validation | medium | FR-UX-3 ("right-size settings") has no acceptance criterion or render mechanism — add one (e.g. settings shown as a single collapsed line with field count, visually lighter than data/screens). | The plan flags `content` as `later` but never operationalizes settings right-sizing; an untestable requirement will silently not ship. | FR-UX-3 | Snapshot: settings occupies ≤1 default line and is visually subordinate to data/screens. |
| R1-F6 | Interfaces | low | Reconcile the header ("**Plan:** `KICKOFF_UX_PLAN.md`") with the plan, which cites "Requirements … (v0.1)" while this doc is v0.3 — pin a matching version so reviewers know the pair is in sync. | Plan header says v0.1; requirements are v0.3 — a stale cross-reference risks review against the wrong baseline. | Requirements front-matter / Plan front-matter | Grep: both docs cite the same requirements version. |
