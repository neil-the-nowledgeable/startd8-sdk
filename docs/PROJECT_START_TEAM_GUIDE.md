# StartD8 Project Start — Team Guide

**Audience:** any team onboarding a project onto the StartD8 SDK (greenfield or brownfield).
**What this is:** the single, canonical walkthrough of the *project-start* experience — from
"idea + data model" to a working app scaffold, plus the optional stakeholder-panel facilitation
and its viewer. It replaces the earlier one-off `STARTD8_PROJECT_INIT_GUIDE.md` +
`PERSONA_DRAFTING_KICKOFF_GUIDE.md` (both predated the project-start distillation and used renamed
commands).
**Currency:** reflects the **post-distillation** CLI (the kernel renamed `concierge` → `kickoff`;
the guided experience; the `kickoff-panel` transcript viewer). If a command below differs from
`startd8 <group> --help`, trust `--help` and file an issue.

> **Per-project quick start:** each pilot repo has a short `docs/STARTD8_START_HERE.md` that says
> *where that repo is today* and *the exact next commands*. Read that first; use this guide for the
> full picture.

---

## 0. Two rules that apply to every command

1. **`$0` vs paid.** Almost everything here is **`$0`, deterministic, no LLM, no network** — the
   CLI labels each command. The only paid (token-spending) commands are: `kickoff guided --agent`,
   `kickoff panel ask` / `ask-all`, the optional `--roles` pass on `requirements elicit` /
   `screens suggest`, and the legacy `kickoff-legacy chat`. Paid commands tell you the cost after
   they run, and degrade cleanly to "no spend / defer" if a key is missing.
2. **Preview vs write.** Read/draft commands **preview by default**; writing requires an explicit
   flag — **`--apply`** (`kickoff instantiate`, `kickoff derive`, `vipp apply`) or an
   **`approve`** verb (`requirements`, `screens`). `review` shows the *literal bytes* a following
   `approve` will write. Nothing runs your app or authors your real product content.

**Prerequisite:** `startd8` on your PATH (`startd8 --help`). If not, run from the SDK checkout:
`PYTHONPATH=/Users/neilyashinsky/Documents/dev/startd8-sdk/src python3 -m startd8.cli …`.

---

## 1. Which path are you on?

| | **Greenfield** (no schema/app yet) | **Brownfield** (existing code/models) |
|---|---|---|
| Orient | `kickoff assess` · optional `kickoff guided` | `kickoff survey` → `kickoff assess` |
| Get a data contract | prose → `generate contract --promote` | `kickoff derive --models <pkg> --apply` |
| Onboard package | `kickoff instantiate --apply` | `kickoff instantiate --apply` (if you want the input package) |
| Ground-truth loop | (skip — nothing to adjudicate) | `project init --with-vipp` → `vipp negotiate` → `vipp apply` |

The **guided experience** (`kickoff guided`) is an optional, additive layer that walks you through
the right path for your project — it **spends and writes nothing** by default; it just prints the
commands to run. It is an *offer*, never a gate.

---

## 2. Orient — see where you are (`$0`, read-only)

```bash
startd8 kickoff survey      # brownfield triage: docs, models, fixtures, PII (read-only)
startd8 kickoff assess      # readiness + the $0-cascade view; offers the guided experience
startd8 kickoff guided      # optional: Orient → Guide → Deepen playbook, prints commands
#   add --agent for a PAID conversational interview (off by default → guided is $0)
```

`assess` accepts `--guided/--no-guided` to force the offer on/off; `--json` on all three for CI.

---

## 3. Onboard — get a data contract + the kickoff input package

**Greenfield** — the schema comes from prose, not from code:
```bash
startd8 kickoff instantiate            # preview the 7-file kickoff input package
startd8 kickoff instantiate --apply    # write it  (--with-authoring adds REQUIREMENTS/PLAN/TEST_USERS)
#   --posture prototype|production (default prototype)
startd8 generate contract --promote    # turn the authored prose into prisma/schema.prisma
```

**Brownfield** — derive the contract from your existing Pydantic models:
```bash
startd8 kickoff derive --models app.models --check     # preview / drift (non-zero exit on drift)
startd8 kickoff derive --models app.models --apply     # write prisma/schema.prisma
#   --models is REQUIRED and repeatable; --pythonpath sets where to import from
```
`derive` is **brownfield-only** (it errors on greenfield — use `generate contract` there).

---

## 4. Draft — requirements & screens (a fast first draft to approve)

These are unchanged from before the distillation. Every suggestion carries **provenance**
(`baseline` = $0 deterministic, `estimate` = role-drafted, `human`), nothing is written without an
explicit `approve`, and the tools **never author your real content** — only shells and stubs.

**Requirements** (`elicit → synthesize → review → approve`):
```bash
startd8 requirements init-roster                 # once; then EDIT docs/kickoff/inputs/stakeholders.yaml
startd8 requirements elicit --brief docs/brief.md        # $0 baseline (schema+brief → FR stubs)
startd8 requirements elicit --brief docs/brief.md --roles # + PAID per-persona pass
startd8 requirements synthesize                  # $0: merge into one coherent doc
startd8 requirements review                      # $0: literal bytes + coverage + grounding flags
startd8 requirements approve docs/design/<feature>/<FEATURE>_REQUIREMENTS.md   # readiness-gated, one-shot
```

**Screens** (composite views + non-entity pages; needs `prisma/schema.prisma`):
```bash
startd8 screens suggest            # $0 baseline (+ optional paid --roles pass)
startd8 screens review             # $0: literal authoring prose + grounding, per screen
startd8 screens approve --all      # apply staged screens → prisma/views.yaml / pages.yaml (accumulates)
startd8 screens reject --name "X"  # drop one (writes nothing)
```

---

## 5. Facilitate — the stakeholder panel (optional, mostly paid)

A roster of stakeholder personas that pressure-tests your strategy. Two levels:

```bash
startd8 kickoff panel list         # $0: show the persona roster (the "mirror")
startd8 kickoff panel ask   …      # PAID: one persona answers (synthetic, unratified)
startd8 kickoff panel ask-all …    # PAID: the whole roster answers
startd8 kickoff panel import …     # $0: ingest an external role/rubric set as a roster
```

The **multi-round facilitated** process (R0–R4: prep → individual → pre-mortem → cross-pollination
→ synthesis) currently runs via `scripts/run_kickoff_panel.py` in the SDK checkout; it writes a
transcript to `.startd8/kickoff-panel/<session>.json`. `startd8 kickoff deepen` is presently a
**pointer** to it. Every persona output is **synthetic and unratified** — a fast draft from a room
full of stakeholders, never a decision.

---

## 6. View — follow the panel transcript (`$0`, read-only)

Once a facilitation transcript exists (`.startd8/kickoff-panel/<session>.json`), the viewer renders
it as a standalone, offline HTML page you can navigate by **round** and by **role**:

```bash
startd8 kickoff-panel list                      # session ids, newest first
startd8 kickoff-panel show [SESSION_ID]          # terminal dump; --by-role to re-pivot; --json for raw
startd8 kickoff-panel view [SESSION_ID] --open   # write + open the HTML viewer (default: newest session)
startd8 kickoff-panel view --watch               # live-follow: auto-updates as rounds land
#   [SESSION_ID] defaults to the newest; --project <root> to point at another repo; --interval N
```

The viewer is **observe-only** — two-axis expand/collapse, per-persona model/family badges,
adversary + grounding markers, the R0 prep cards, the halted-panel state, and a persistent
"synthetic / unratified" banner. No scoring, no acceptance, no write-back (you ratify elsewhere).

---

## 7. Brownfield: the VIPP ground-truth loop

VIPP is the project-side negotiator: a producer serializes onboarding **proposals** to
`.startd8/vipp/proposals-inbox.json`; you **negotiate** them against your project's ground truth,
then **apply** the accepted ones at your own privilege. Ground truth *adjudicates*, never
*originates* — so on a healthy project this is often a clean no-op.

```bash
startd8 project init --with-vipp        # establish the VIPP posting (or: startd8 vipp init)
startd8 vipp negotiate                   # $0 deterministic dispositions.{json,md}
startd8 vipp apply                       # preview; add --apply to write accepted proposals
```

> During the deprecation window, bare `startd8 project init` still posts VIPP **by default** with a
> notice. Prefer the explicit `--with-vipp` so you don't depend on the default flipping later.

---

## 8. Generate the app (the `$0` cascade)

Once you have `prisma/schema.prisma`, the deterministic cascade builds the app — **no LLM**:
```bash
startd8 generate backend --check    # Pydantic + SQLModel + FastAPI + HTMX modular monolith
startd8 generate views --schema prisma/schema.prisma --views prisma/views.yaml …
startd8 polish apply --project <out> --theme <theme>    # accessible design system
startd8 wireframe                   # $0 pre-generation summary of what the cascade will build
```
(See the SDK `CLAUDE.md` "generation scope" section for the bucket separation — the SDK builds the
application skeleton; it never authors your real user-facing content.)

---

## 9. Deprecated command names (don't build on these)

The distillation renamed several groups. Old names still work **for one release** (with a stderr
notice) but will be removed:

| Old (deprecated) | Use instead |
|---|---|
| `startd8 concierge …` (hidden) | `startd8 kickoff …` |
| `startd8 panel …` (hidden) | `startd8 kickoff panel …` |
| `startd8 kickoff plan` / `kickoff next` | `startd8 kickoff guided` (now under `kickoff-legacy`) |
| `startd8 kickoff-legacy …` | the canonical `kickoff …` kernel + `kickoff guided` |
| `startd8 project init` (bare, greenfield onboarding) | `startd8 kickoff instantiate --apply` |

`startd8 requirements …`, `startd8 screens …`, and `startd8 vipp …` are **unchanged**.

---

## 10. Cheat sheet

| Goal | Command | Cost |
|---|---|---|
| See where I am | `kickoff survey` / `kickoff assess` / `kickoff guided` | $0 |
| Data contract (greenfield) | `generate contract --promote` | $0 |
| Data contract (brownfield) | `kickoff derive --models <pkg> --apply` | $0 |
| Kickoff input package | `kickoff instantiate --apply` | $0 |
| Draft requirements | `requirements elicit --brief b.md [--roles]` → `synthesize` → `review` → `approve` | $0 / paid |
| Decide screens | `screens suggest [--roles]` → `review` → `approve --all` | $0 / paid |
| Run the panel | `kickoff panel ask-all …` / `scripts/run_kickoff_panel.py` | paid |
| **View the panel** | `kickoff-panel view [--watch]` / `show [--by-role]` / `list` | $0 |
| Brownfield ground truth | `project init --with-vipp` → `vipp negotiate` → `vipp apply --apply` | $0 |
| Build the app | `generate backend` → `generate views` → `polish apply` | $0 |

**Everything** takes `--project <path>` (default `.`) and `--json` on read/emit commands.
