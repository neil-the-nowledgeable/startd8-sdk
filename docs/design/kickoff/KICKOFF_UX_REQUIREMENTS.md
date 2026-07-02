# Kickoff UX / Information Architecture — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
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

- **FR-UX-1 — The four-things mental model.** The kickoff is presented as **four things the user provides**,
  plain-named, in dependency order, with a one-line "what it is":
  1. **Your data** — the things your app stores (→ the schema).
  2. **Your screens** — the pages & views built from your data.
  3. **Your settings** — a few choices (language, money format, budget…) — *small, mostly defaults*.
  4. **Placeholder content** — starter copy/test data (optional, later).
  Plus **Build** — the `$0` generate step, shown as the destination, not a "thing to author".
- **FR-UX-2 — A single plain-language glossary (owned here).** One table maps every internal term to its
  user-facing name, and is the **single source** all surfaces cite: `data_model`→"Your data",
  `manifests`→"Your screens", `value_inputs`→"Your settings", `cascade`→"Build", `content`→"Placeholder
  content"; drop metaphors ("front bookend", "buckets 2/4") from user-facing copy. Internal names remain
  in `--json`/`--verbose` for scripting.
- **FR-UX-3 — Right-size the "settings" bucket.** The presentation must convey that *settings* is small
  (≈8 fields, mostly dropdowns with sane defaults) and not equal-weight with data/screens, so the user
  isn't scared by it. (The real work is data → screens.)

### B. The status view (`startd8 kickoff red-carpet`, read-only)

- **FR-UX-4 — Focused summary + one next action.** The default status view shows: a one-line progress
  header (spine + one headline %), the four-things map with a clear "**you are here**", and **the single
  highest-value next action** (plain language + its command). Nothing else by default.
- **FR-UX-5 — Progressive disclosure.** The full advisory list and the ranked playbook move behind
  `--verbose`; the machine payload stays on `--json` (unchanged shape). The default view ends with a
  one-line pointer ("N more details → `--verbose`").
- **FR-UX-6 — One progress spine, no triple redundancy (UX-P3).** The stage map, advisories, and playbook
  are rendered as **one** progress spine (the four things + Build, each with a compact status), not three
  parallel lists. A gap is named once.
- **FR-UX-7 — Reconcile the two percentages.** Exactly **one** headline number is shown by default (the
  user-fillable **completion %**, FR-WD-2 — the one that answers "how done am I"). The coarse
  `readiness_score` is either dropped from the headline or shown only under `--verbose` with a label.
- **FR-UX-8 — Calm greenfield (UX-P4).** A blank project reads as "not started — begin with **Your data**",
  not as red "Cascade blocker" errors. Severity/color maps to user urgency: a fresh project's headline is
  informational, not error-colored.

### C. The wizard (`--wizard`)

- **FR-UX-9 — One step at a time (no status wall).** The wizard does **not** print the full status view.
  It opens with a one-line framing, then renders **one step**: a compact spine (Step N of M · plain name),
  the **found / needed / action** triple in plain language, and the confirm prompt. On advance, the next
  step — never the whole wall.
- **FR-UX-10 — Plain-language step copy.** The wizard's found/needed/action uses the glossary (FR-UX-2):
  "Found 3 model files… → I can build **Your data** from them. Apply? [y/N]", not "propose schema kind".
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

*v0.3 — Post lessons-learned hardening. Applied 3 SDK design-docs lessons: Leg-1 #5 (single-source
`GLOSSARY` ownership + no-jargon enforcement — directly on point for a vocabulary spec), phantom-reference
audit (all symbols verified; new ones marked to-be-created), CRP steering (named the target + settled
items). No scope pruned. Ready for CRP.*
