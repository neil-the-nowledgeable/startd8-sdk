# StartD8 Project Start — Team Guide

**A guided path from "idea + data model" to a working app scaffold** — orient, draft your
requirements and screens, optionally pressure-test with the stakeholder panel, and generate the
app. Written for a **new project**; if you already have code, there's a short brownfield section
near the end.

> If a command differs from `startd8 <group> --help`, trust `--help`. Each repo also has a short
> `docs/STARTD8_START_HERE.md` with its exact next commands.

---

## 1. Orient — see where you are (`$0`, read-only)

```bash
startd8 kickoff assess      # readiness + the $0-cascade view; offers the guided experience
startd8 kickoff guided      # optional: a walkthrough that just prints the commands to run
#   add --agent for a PAID conversational interview (off by default → guided is $0)
```

The guided experience **spends and writes nothing** by default — it's an offer, never a gate.
`--json` on both for CI.

---

## 2. Onboard — get a data contract + the kickoff input package

On a new project the schema comes from your prose, not from code:

```bash
startd8 kickoff instantiate            # preview the 7-file kickoff input package
startd8 kickoff instantiate --apply    # write it  (--with-authoring adds REQUIREMENTS/PLAN/TEST_USERS)
#   --posture prototype|production (default prototype)
startd8 generate contract --promote    # turn the authored prose into prisma/schema.prisma
```

---

## 3. Draft — requirements & screens

A fast first draft for you to approve. Every suggestion carries **provenance** (`baseline` = $0
deterministic, `estimate` = role-drafted, `human`), nothing is written without an explicit
`approve`, and the tools **never author your real content** — only shells and stubs.

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

## 4. Facilitate — the stakeholder panel (optional, mostly paid)

A roster of stakeholder personas that pressure-tests your strategy. Two levels:

```bash
startd8 kickoff panel list         # $0: show the persona roster (the "mirror")
startd8 kickoff panel ask   …      # PAID: one persona answers (synthetic, unratified)
startd8 kickoff panel ask-all …    # PAID: the whole roster answers
startd8 kickoff panel import …     # $0: ingest an external role/rubric set as a roster
```

The **multi-round facilitated** process (R0–R4: prep → individual → pre-mortem → cross-pollination
→ synthesis) currently runs via `scripts/run_kickoff_panel.py` in the SDK checkout; it writes a
transcript to `.startd8/kickoff-panel/<session>.json`. Every persona output is **synthetic and
unratified** — a fast draft from a room full of stakeholders, never a decision.

---

## 5. View — follow the panel transcript (`$0`, read-only)

Once a facilitation transcript exists, the viewer renders it as a standalone, offline HTML page you
can navigate by **round** and by **role**:

```bash
startd8 kickoff-panel list                      # session ids, newest first
startd8 kickoff-panel show [SESSION_ID]          # terminal dump; --by-role to re-pivot; --json for raw
startd8 kickoff-panel view [SESSION_ID] --open   # write + open the HTML viewer (default: newest session)
startd8 kickoff-panel view --watch               # live-follow: auto-updates as rounds land
#   [SESSION_ID] defaults to the newest; --project <root> to point at another repo
```

The viewer is **observe-only** — two-axis expand/collapse, per-persona model/family badges,
adversary + grounding markers, the R0 prep cards, and a persistent "synthetic / unratified" banner.
No scoring, no acceptance, no write-back.

---

## 6. Generate the app (the `$0` cascade)

Once you have `prisma/schema.prisma`, the deterministic cascade builds the app — **no LLM**:

```bash
startd8 generate backend --check    # Pydantic + SQLModel + FastAPI + HTMX modular monolith
startd8 generate views --schema prisma/schema.prisma --views prisma/views.yaml …
startd8 polish apply --project <out> --theme <theme>    # accessible design system
startd8 wireframe                   # $0 pre-generation summary of what the cascade will build
```

The SDK builds the application skeleton; it never authors your real user-facing content.

---

## 7. Good to know — `$0` vs paid, preview vs write

- **`$0` vs paid.** Almost everything is **`$0`, deterministic, no LLM** — the CLI labels each. The
  only paid commands are `kickoff guided --agent`, `kickoff panel ask` / `ask-all`, and the optional
  `--roles` pass on `requirements elicit` / `screens suggest`. Paid commands report their cost after
  running and degrade cleanly to "no spend / defer" if a key is missing.
- **Preview vs write.** Reads preview by default; **writing needs `--apply`** (`kickoff instantiate`,
  `generate contract --promote`) or an `approve` verb (`requirements`, `screens`). `review` shows the
  literal bytes `approve` will write. Nothing runs your app or authors your real content.
- **Prerequisite.** `startd8` on your PATH (check with `startd8 --help`).

---

## 8. Deprecated command names (don't build on these)

Some groups were renamed; old names still work **for one release** (with a stderr notice) but will
be removed:

| Old (deprecated) | Use instead |
|---|---|
| `startd8 concierge …` (hidden) | `startd8 kickoff …` |
| `startd8 panel …` (hidden) | `startd8 kickoff panel …` |
| `startd8 kickoff plan` / `kickoff next` | `startd8 kickoff guided` |
| `startd8 project init` (bare, greenfield onboarding) | `startd8 kickoff instantiate --apply` |

`startd8 requirements …`, `startd8 screens …`, and `startd8 vipp …` are **unchanged**.

---

## 9. Working with an existing codebase (brownfield)

If you already have code and models, three things differ from the new-project flow above; the rest
(Draft, Facilitate, View, Generate) is identical.

**Orient with a triage** instead of a bare `assess`:
```bash
startd8 kickoff survey      # docs, models, fixtures, PII (read-only)
```

**Derive the data contract from your existing Pydantic models** (instead of `generate contract`):
```bash
startd8 kickoff derive --models app.models --check     # preview / drift (non-zero exit on drift)
startd8 kickoff derive --models app.models --apply     # write prisma/schema.prisma
#   --models is REQUIRED and repeatable; --pythonpath sets where to import from
```
`derive` is brownfield-only (it errors on a greenfield project).

**Run the VIPP ground-truth loop** — negotiate onboarding proposals against your project's ground
truth, then apply the accepted ones at your own privilege. Ground truth *adjudicates*, never
*originates*, so on a healthy project this is often a clean no-op:
```bash
startd8 project init --with-vipp        # establish the VIPP posting (or: startd8 vipp init)
startd8 vipp negotiate                   # $0 deterministic dispositions.{json,md}
startd8 vipp apply                       # preview; add --apply to write accepted proposals
```

---

## 10. Cheat sheet

| Goal | Command | Cost |
|---|---|---|
| See where I am | `kickoff assess` / `kickoff guided` | $0 |
| Kickoff input package | `kickoff instantiate --apply` | $0 |
| Data contract | `generate contract --promote` | $0 |
| Draft requirements | `requirements elicit --brief b.md [--roles]` → `synthesize` → `review` → `approve` | $0 / paid |
| Decide screens | `screens suggest [--roles]` → `review` → `approve --all` | $0 / paid |
| Run the panel | `kickoff panel ask-all …` / `scripts/run_kickoff_panel.py` | paid |
| **View the panel** | `kickoff-panel view [--watch]` / `show [--by-role]` / `list` | $0 |
| Build the app | `generate backend` → `generate views` → `polish apply` | $0 |
| Brownfield: data contract | `kickoff derive --models <pkg> --apply` | $0 |
| Brownfield: ground truth | `project init --with-vipp` → `vipp negotiate` → `vipp apply --apply` | $0 |

**Everything** takes `--project <path>` (default `.`) and `--json` on read/emit commands.
