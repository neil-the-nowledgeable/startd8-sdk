# Kickoff UX / Information Architecture — Requirements

**Version:** 0.7 (Output hygiene & orientation — implementation refinement)
**Date:** 2026-07-06
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
- **UX-P5 — This spec owns presentation; it never changes *generation* mechanism.** No new backend
  generation behavior, grammar, or write path. It re-shapes what `build_red_carpet_state`/the advisor/the
  wizard already produce. *(v0.5 refinement: §3E extends this doc's reach into the CLI **output/logging
  hygiene** layer — console log level, a `--debug` toggle, the banner — which is output presentation, not
  generation mechanism. The generation/backend invariant above is unchanged.)*
- **UX-P6 — Quiet by default; diagnostics on request.** The terminal is the user's workspace, not a log
  sink. Operational/diagnostic logging (logger names, timestamps, INFO traces) is **hidden by default** and
  available **on demand** (`--debug`/env var). Only user-relevant `WARNING`/`ERROR` surface unbidden. Every
  line the user sees by default must earn its place by helping them understand *what* is happening and
  *why*.

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

### E. Output hygiene & orientation (v0.5)

> **Scope note.** FR-UX-13/14 are **CLI output/logging-hygiene** requirements. Their root cause is
> **global**, not kickoff-local: `get_logger()` → `_ensure_default_log_file_handler()` attaches a console
> `StreamHandler(sys.stderr)` at **INFO** to the root `startd8` logger (`logging_config.py:229-238`), so
> **every** SDK `logger.info(...)` (e.g. `concierge/core.py:244` → `startd8.concierge.core - INFO -
> concierge.survey root=…`) prints to the user's terminal during *any* command. The fix therefore lives at
> the CLI-logging layer and applies **CLI-wide** (all user-facing commands quiet-by-default); kickoff is the
> surface that **exercises and verifies** it. FR-UX-15/16 are kickoff-scoped presentation requirements.
>
> **Cross-command pointer (CRP R2-F2).** Because FR-UX-13/14 change **console behavior for every CLI
> command** (not just kickoff) — applied **once** at the root seam (`cli.py:64` `_bootstrap`), never
> per-command — this is recorded here as the owning spec, but the change is CLI-wide: any command owner who
> greps for CLI logging behavior should find this pointer. An **"applied-once" invariant** (the seam runs
> exactly once per process) is a plan-side test (Step 8).

- **FR-UX-13 — Diagnostic log lines are off by default (CLI-wide).** During normal interactive use the CLI
  must **not** emit Python-logging plumbing lines — the `%(asctime)s - %(name)s - %(levelname)s -
  %(message)s` stream (`logging_config.py:125-127,233-236`), e.g. `2026-07-06 11:54:57 -
  startd8.concierge.core - INFO - concierge.survey root=/…`. Such lines carry no end-user value: logger
  names, timestamps, and module paths are diagnostics, not guidance. **Requirement:** the default **console
  handler** level for interactive CLI invocations is **`WARNING`**, so `INFO`/`DEBUG` records do not reach the
  terminal. `WARNING`/`ERROR` **do** reach the console (users must see real problems — consistent with the
  FR-UX-5 error exception). **Fidelity caveat (CRP R2-F1):** "records still flow to the file
  (`~/.startd8/logs/startd8.log`) and OTel" holds **only if the `startd8` *logger* level is at `DEBUG`** —
  Python drops records below the *logger's* own level **before any handler**, and today
  `_ensure_default_log_file_handler()` pins the logger at `INFO` (`logging_config.py:242`). So the quiet
  default is a **handler-level** change (console → `WARNING`) that must **keep the logger at `DEBUG`** for the
  file/OTel sinks to retain full fidelity. **Error-visibility guarantee (CRP R2-F5):** the FR-UX-5
  error advisories `--check` gates on are printed via the Rich `console` (stdout), **not** via `logger.*`, so
  no console-handler level can hide them *by construction* — the human view and `--check` cannot diverge.
  This is a **distinct axis from `--verbose`** (FR-UX-5 = domain advisory/playbook *detail*; FR-UX-13 =
  logging *plumbing*): the two never share a flag, and turning one on must not turn the other on.
- **FR-UX-14 — A `--debug` toggle (flag + env) restores full diagnostics.** Troubleshooting must remain
  possible. Both a **`--debug` flag** on the kickoff command *and* an **environment variable** raise the
  **console handler** level back to `DEBUG`, restoring the full `<ts> - <logger> - <level> - <msg>` stream.
  **Logger-gate requirement (CRP R2-F1):** because the `startd8` logger is pinned at `INFO`
  (`logging_config.py:242`), raising the *console handler* alone surfaces `INFO` but **never `DEBUG`** — so
  `--debug` must **also lower the `startd8` logger level to `DEBUG`**, else `logger.debug(...)` is dropped
  before any handler and "restore full diagnostics" is unmet.
  **Precedence:** an explicit `--debug` **or** `STARTD8_DEBUG=1` overrides the FR-UX-13 quiet default; the
  existing **`STARTD8_LOG_LEVEL`** continues to take precedence over both (it already gates console level at
  `logging_config.py:230,242`). `--debug` is **independent of and composable with** `--verbose`/`--json`
  (debug = plumbing verbosity; `--verbose` = domain detail; `--json` = machine payload). Help text names all
  three roles so their separation is discoverable (extends FR-UX-11).
- **FR-UX-15 — Every step shows only what's needed — with the "why".** Building on FR-UX-4/9/10: each
  surface (status view and each wizard step) presents the **minimum the user needs to act**, and every shown
  element carries enough context for the user to understand **what** is happening **and why**. The single
  next action states not just the command but its **reason** ("Author your data first — your screens and
  settings are built from it"), glossary-plain (FR-UX-2) and one line. No raw internal state, no plumbing,
  no unexplained numbers. Depth and rationale-in-detail stay behind `--verbose`. **Acceptance — the exact
  element→why set (CRP R2-F4)** (so a snapshot is unambiguous; `headline()` has no why-clause today,
  `presentation.py:142-146`): **next action** → a full one-line why-clause; **pct label** → the FR-UX-7
  "not yet buildable / N defaulted" annotation *is* its why; **error banner** → "N problem(s) → `--verbose`";
  **spine nodes** → plain name only (no why needed). A snapshot asserts each enumerated element carries its
  named why-string and `has_jargon()` passes on every why; nothing else appears that the user cannot act on
  or interpret.
- **FR-UX-16 — A high-level intro banner on every human-facing invocation.** Every human-facing kickoff
  invocation **opens with a concise, visually distinct banner** that orients the user and makes the output
  easier to scan: a one-line statement of what kickoff is, the three-things-plus-Build mental model
  (FR-UX-1) at a glance, and how to go deeper. **One shared renderer** (`render_intro_banner`) so every
  surface shows a **byte-identical** banner (CRP R2-S4). Rendered inside a rule/panel so it reads as a
  header, and **precedes** the focused output.
  - **Source (implementation-corrected):** the banner is the content contract's dedicated **`<!-- BANNER -->`
    slice** — `load_experience_doc("intro", section="banner")` — a tight block *distinct from* the fuller
    `TL;DR`/`explain` content. Implementation found the packaged TL;DR is **~17 lines**, so a compact-TL;DR
    banner would blow the budget (the R2-F3 discovery, resolved by a purpose-built slice rather than reusing
    TL;DR).
  - **Surfaces (enumerated for testability).** The banner shows on **bare `kickoff`** and every human-facing
    status/action command — **`survey`, `assess`, `instantiate`, `derive`, `confirm`, `log-friction`**, and
    **`red-carpet`** (all its human modes). It is **suppressed under `--json`** (machine output stays clean)
    and under `red-carpet --check` (CI signal).
  - **Exempt** (these already surface the intro/instructional content — a banner would duplicate it):
    **`explain`** (renders the full doc the banner is sliced from) and the guided **`guided`/`deepen`** flow
    (its Orient phase renders the intro).
  - **Constraints:** compact (≤ ~6 lines — must not reintroduce the FR-UX-4 overload), glossary-plain
    (FR-UX-2). **Acceptance:** a snapshot of any banner-bearing command shows the banner first, ≤ ~6 lines,
    no jargon tokens; `--json` output contains no banner; the exempt commands show no duplicate banner.
  - **Source-level budget (CRP R2-F3):** because a `section`/`compact` slice **falls back to the full doc**
    when its block is absent (`concierge/writes.py`), the ≤6-line budget is **also asserted on the packaged
    `<!-- BANNER -->` block itself** (present *and* ≤ ~6 lines), not only on the render.

---

## 4. Non-Requirements

- **NR-1 — No new backend feature / grammar / write path.** Generation behavior is untouched;
  `build_red_carpet_state`, the advisor, the completion model, and the wizard proposals are unchanged.
  *(v0.5: FR-UX-13/14 change the CLI **console log level default** and add a `--debug` toggle — an
  output-hygiene change at the logging layer, not a generation/backend behavior change. `INFO`/`DEBUG`
  records still reach the file/OTel sinks; only their **console visibility** changes. **This IS a CLI-wide
  console-behavior change for all commands** (CRP R2-F2) — "no backend change" is not "no behavior change"; it
  is scoped to console output hygiene, applied once at the root seam.)*
- **NR-6 — `--debug` is not `--verbose`, and neither raises the other.** The two flags stay separate axes
  (FR-UX-13/14); no change collapses them into one setting.
- **NR-7 — The quiet *default* never suppresses `WARNING`/`ERROR`** *(scoped, CRP R2-F5)*. In the
  **default (env-unset)** case FR-UX-13 lowers only `INFO`/`DEBUG` console visibility; real problems still
  print. The absolute is scoped to the default: a user who **explicitly** sets `STARTD8_LOG_LEVEL=ERROR`
  (honored verbatim, FR-UX-14 precedence) *does* suppress `WARNING` at the console — that is a deliberate
  user override, not the quiet default. Independently, the FR-UX-5 error advisories are **console-printed,
  not `logger`-emitted**, so they print regardless of any console-handler level (FR-UX-13 guarantee).
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

*v0.7 — Implementation refinement (no new review round). FR-UX-16 updated to match what shipped: the banner
is a **purpose-built `<!-- BANNER -->` slice** (`section="banner"`), not the `compact=True` TL;DR — the packaged
TL;DR proved to be ~17 lines, so R2-F3's budget concern is resolved by a dedicated slice rather than reusing
TL;DR. FR-UX-16 now **enumerates its surfaces** (bare `kickoff` + `survey`/`assess`/`instantiate`/`derive`/
`confirm`/`log-friction`/`red-carpet`, `--json`/`--check` suppressed) and its **exemptions** (`explain`,
`guided`/`deepen` — self-orienting content surfaces), so "every invocation" is testable. Drives the
kernel-subcommand banner wiring (plan Step 11).*

*v0.6 — Post-CRP R2 (reviewer claude-opus-4-8, v0.5-scoped; 5 F + 5 S, all code-grounded, **all accepted**).
Two high-severity corrections re-verified against the bytes: (R2-F1/S1) the `startd8` **logger** is pinned at
`INFO` (`logging_config.py:242`) so a console-handler-only fix drops `DEBUG` before any sink — FR-UX-13/14
now require lowering the **logger** level, and the "full fidelity" claim is caveated; (R2-S2) `cli.py` imports
`.framework/.agents/.benchmark/.providers` **before** `logging_config`, so the import-time guard must move
above them (plan Step 8). Also: FR-UX-13 gains an **error-visibility guarantee** (FR-UX-5 advisories are
Rich-`console`-printed, not `logger`-emitted → uncloseable by any handler level — R2-F5); NR-7 scoped to the
env-unset default; NR-1 + §3E name the **CLI-wide** console change and add a cross-command pointer (R2-F2);
FR-UX-15 enumerates the element→why set (R2-F4); FR-UX-16 adds a **source-level** TL;DR budget assert since
`compact=True` falls back to full text (R2-F3). Dispositions in Appendix A; R2 verbatim in Appendix C. Ready
for implementation.*

*v0.5 — Output hygiene & orientation. Adds §3E (FR-UX-13..16) + UX-P6 in response to real terminal noise:
diagnostic Python-logging lines (`… - startd8.concierge.core - INFO - concierge.survey root=…`) leaking to
the user because `get_logger()` attaches an **INFO console handler CLI-wide** (`logging_config.py:229-238`).
**FR-UX-13** makes the CLI quiet-by-default (console → `WARNING`; `INFO`/`DEBUG` to file/OTel only), a
**distinct axis** from `--verbose`. **FR-UX-14** adds a `--debug` flag **and** env toggle (`STARTD8_DEBUG`;
`STARTD8_LOG_LEVEL` still wins) to restore full diagnostics. **FR-UX-15** requires every default-view element
to carry a plain-language "what + why". **FR-UX-16** adds a compact high-level intro banner on every
invocation (content-contract-sourced, `--json`-suppressed). Scope note: FR-UX-13/14 are a CLI-logging-layer
change (output hygiene, not generation mechanism) — UX-P5 refined, NR-1 clarified, NR-6/7 added. Decisions
locked with the sponsor: **CLI-wide** suppression, **flag + env** toggle, **banner every invocation**.
Pre-CRP — recommend a CRP round before implementation.*

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

> Triage R2 (orchestrator, 2026-07-06). **v0.5 additions only — all 5 F + 5 S accepted; none rejected** —
> grounded in `logging_config.py` (logger-gate `:242`), `cli.py` (import order `:20-25`), `concierge/writes.py`
> (`:130+`), `cli_concierge.py` (`_kickoff_root`). The two high-severity items (logger-level gate, import
> order) were re-verified against the bytes before accepting.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R2-F1 | Lower the `startd8` **logger** level to DEBUG, not only the console handler ("full fidelity" was false) | CRP R2 | FR-UX-13 fidelity caveat + FR-UX-14 logger-gate requirement; plan Step 7 (R2-S1) | 2026-07-06 |
| R2-F2 | Name the CLI-wide console-behavior change + cross-command pointer; reword NR-1 | CRP R2 | §3E cross-command pointer; NR-1; applied-once invariant → plan Step 8 | 2026-07-06 |
| R2-F3 | Assert packaged intro has a `<!-- TL;DR -->` block ≤ ~6 lines (source-level; compact falls back to full) | CRP R2 | FR-UX-16 source-level budget; plan Step 10 (R2-S5) | 2026-07-06 |
| R2-F4 | Enumerate the exact default-view element→why set (untestable otherwise) | CRP R2 | FR-UX-15 acceptance (next-action/pct/banner/spine) | 2026-07-06 |
| R2-F5 | Scope NR-7 to the default (env-unset) case; assert error advisories are console-printed not logger-emitted | CRP R2 | NR-7; FR-UX-13 error-visibility guarantee | 2026-07-06 |
| R2-S1 | Step 7 also lowers the logger level to DEBUG | CRP R2 | plan Step 7 (mirrors R2-F1) | 2026-07-06 |
| R2-S2 | Move logging import + import-time guard above the heavy imports (`cli.py:20-23`) | CRP R2 | plan Step 8 | 2026-07-06 |
| R2-S3 | Harden the console-handler locator (zero-handler early-return `:181`; mutate all non-File StreamHandlers) | CRP R2 | plan Step 7 | 2026-07-06 |
| R2-S4 | Unify the banner renderer (Panel vs `_render_markdown`) for byte-consistency | CRP R2 | plan Step 9 | 2026-07-06 |
| R2-S5 | Source-level TL;DR budget test + no-double-render (group callback + subcommand) test | CRP R2 | plan Step 10 (mirrors R2-F3) | 2026-07-06 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| *None.* All R1 + R2 suggestions were code-grounded and accepted. |  |  |  |  |

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

#### Review Round R2 — claude-opus-4-8 — 2026-07-06

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-06 16:45:00 UTC
- **Scope**: v0.5 additions only (§3E FR-UX-13..16 + UX-P6), weighted per the sponsor focus file. Code-grounded in `logging_config.py` (INFO console handler + logger-level gate), `cli.py` (`_bootstrap`/import order), `cli_concierge.py` (`_kickoff_root`), `concierge/writes.py` (`load_experience_doc`), `kickoff_experience/presentation.py`. FR-UX-1..12 not re-litigated.

##### Sponsor focus asks (answered first)

**Ask 1 — FR-UX-13 blast radius vs. the doc's home.**
- **Summary answer:** **Partial** — mechanically safe (one seam), but doc-placement is risky and NR-1 understates it.
- **Rationale:** The change is applied once at the single root seam (`cli.py:64` `_bootstrap` + one import-time call), so "applied once, not per-command" is achievable. But it silently changes console behavior for **every** CLI command, and it lives in a *kickoff* doc where other command owners won't see it. NR-1 says "no backend behavior change" — true — but this **is** a CLI-wide *console* behavior change for all commands, which the requirement should name explicitly.
- **Assumptions / conditions:** the seam is invoked exactly once (see Ask 2 ordering hazard).
- **Suggested improvements:** Add a CLI-logging companion pointer/requirement (see R2-F2) and an "applied-once" invariant test. Reword NR-1 to acknowledge the CLI-wide console change.

**Ask 2 — Mechanism correctness of quiet-by-default.**
- **Summary answer:** **No, not as specified** — mutating only the console handler level is insufficient, and the import ordering is defeated by cli.py's own import order.
- **Rationale:** `_ensure_default_log_file_handler` sets the **root `startd8` logger** level to `INFO` (`logging_config.py:242`). Python drops records below the *logger's* level **before** any handler, so DEBUG records never reach the file/OTel sinks — contradicting FR-UX-13's "full fidelity retained" — and `--debug` (which per plan Step 7 only raises the *console handler* to DEBUG) surfaces INFO but **never** DEBUG, breaking FR-UX-14's "restore full diagnostics." Separately, cli.py imports `.framework/.agents/.benchmark/.providers` at **lines 20-23 before** `logging_config` at **line 25**, so any import-time `logger.info` in those modules leaks before a line-25-anchored guard runs. `--debug` is indeed too late for import-time logs (only `STARTD8_DEBUG` catches them — the plan acknowledges this residual, but not the logger-level gap).
- **Assumptions / conditions:** env unset (default path).
- **Suggested improvements:** See R2-F1 (lower the logger level, not just the console handler). Plan-side: R2-S1/S2/S3.

**Ask 3 — Interaction with existing axes and NR-6/7.**
- **Summary answer:** **Yes, the axes hold** — and are *stronger* than the doc claims, with one env caveat.
- **Rationale:** The FR-UX-5 error advisories that `--check` fails on are printed via the Rich `console` (stdout) in `cli_kickoff.py`, **not** via `logger.*` — so the FR-UX-13 logging-handler level **cannot** hide them *by construction* (a reassuring, code-grounded fact the doc should assert). `--verbose` (domain detail) and `--debug` (logging plumbing) touch disjoint code, so NR-6 holds. Caveat: NR-7 states an **absolute** ("never suppresses WARNING/ERROR"), but `STARTD8_LOG_LEVEL=ERROR` (which the plan honors verbatim) *would* suppress WARNING at the console — so NR-7 must be scoped to the default (env-unset) case.
- **Assumptions / conditions:** error advisories stay console-printed (they are today).
- **Suggested improvements:** R2-F5.

**Ask 4 — Testability of FR-UX-15/16.**
- **Summary answer:** **Partial** — both need tighter acceptance anchors; FR-UX-16's budget is not guaranteed by its source.
- **Rationale:** FR-UX-16 sources the banner from `load_experience_doc("intro", compact=True)`, which **falls back to the full doc text if the packaged intro lacks a `<!-- TL;DR -->` block** (`concierge/writes.py:130+`) — so the "≤ ~6 lines" budget can silently blow, re-creating the FR-UX-4 overload it exists to prevent (Risk R6). FR-UX-15's "every element carries a what+why" doesn't enumerate *which* elements need a why-string, so a snapshot can't be written unambiguously (the existing `headline()` next-action has no why-clause today — `presentation.py:142-146`).
- **Assumptions / conditions:** none.
- **Suggested improvements:** R2-F3 (assert the packaged intro has a bounded TL;DR block, source-level), R2-F4 (enumerate the element→why set).

##### Feature Requirements Suggestions (first pass)

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | high | FR-UX-13/14 must require lowering the **`startd8` logger level to DEBUG** (not only the console-handler level). State that "full fidelity retained" holds only if the logger gate is at DEBUG; otherwise DEBUG records are dropped and `--debug` cannot restore them. | `logging_config.py:242` pins the root logger at `INFO`; Python drops sub-level records before any handler, so file/OTel never see DEBUG and `--debug` (console→DEBUG) still shows only INFO. | FR-UX-13 (fidelity clause) + FR-UX-14 (`--debug` restores) | Unit: a planted `logger.debug(...)` appears in `~/.startd8/logs/startd8.log` and, under `--debug`, on the console. |
| R2-F2 | Architecture | medium | Add a companion CLI-logging requirement (or an explicit cross-command pointer) noting FR-UX-13/14 changes console behavior for **all** commands, applied once at the root seam; and reword NR-1 to acknowledge the CLI-wide console change (not only "no backend change"). | The change is CLI-wide but buried in a kickoff doc; other command owners won't discover it (Ask 1). | §3E scope note + NR-1 | Grep: a CLI-logging pointer exists; NR-1 names the console-wide scope. |
| R2-F3 | Validation | medium | FR-UX-16 acceptance must assert the **packaged intro doc contains a `<!-- TL;DR -->` block that is ≤ ~6 lines** (source-level), not only that the rendered banner is short — because `compact=True` falls back to full text when the block is absent. | `load_experience_doc(..., compact=True)` falls back to the full doc (`writes.py:130+`); a missing/oversized TL;DR silently violates the ≤6-line budget (Risk R6). | FR-UX-16 (Constraints/Acceptance) | Test on the packaged intro asset: TL;DR present and line count ≤ ~6. |
| R2-F4 | Validation | medium | FR-UX-15 must enumerate the exact default-view **element→why** set (e.g. next-action: full why-clause; pct-label: the "not yet buildable" annotation serves as its why; error banner: "N problems → --verbose"; spine nodes: name only). | "Every element carries a what+why" is untestable without the element list; `headline()` next-action has no why today (`presentation.py:142-146`). | FR-UX-15 (Acceptance) | Snapshot asserts each enumerated element carries its named why-string; `has_jargon()` passes on every why. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F5 | Risks | low | Scope NR-7 to the **default (env-unset)** case and add that FR-UX-5 error advisories are **console-printed, not logger-emitted**, so FR-UX-13 cannot hide them by construction. | `STARTD8_LOG_LEVEL=ERROR` (honored verbatim by plan Step 7) would suppress WARNING, contradicting NR-7's absolute; the console-print fact is the real guarantee for `--check` parity (Ask 3). | NR-7 + FR-UX-5 note | Test: error advisory prints regardless of console handler level; `STARTD8_LOG_LEVEL=ERROR` documented as an explicit override of NR-7. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — all R1-F items are already triaged into Appendix A; no untriaged prior items remain.
