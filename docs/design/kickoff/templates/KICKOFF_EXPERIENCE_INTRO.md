<!-- BANNER -->
**Kickoff** sets up the inputs your app's build needs and can't invent.
You provide three things — **Your data** → **Your screens** → **Your settings** — then **Build** ($0).
Machines draft; you decide. Add `--verbose` for more detail, or `--debug` to see logs.
<!-- /BANNER -->
<!-- TL;DR -->
**Kickoff** collects the inputs the build genuinely needs and cannot invent — what the business
wants, what "good" looks like in numbers, what conventions to follow, the budget, and how the app
is watched. Machines draft and translate; humans validate and decide. Every input is tracked with a
status and a provenance, so the build is always honest about what's real.

**Start here:**  `survey` → `assess` → `instantiate` → then the $0 cascade (`generate …`).

- `startd8 kickoff survey` — read-only triage of what's already in the project ($0).
- `startd8 kickoff assess` — readiness report: which inputs are present, and what's blocking ($0).
- `startd8 kickoff instantiate --posture <prototype|production>` — write the kickoff input package
  (intro, per-domain explainer, and pre-filled `inputs/*.yaml`) into the project.
- `startd8 kickoff guided` — the same path, walked step by step (Orient → Guide → Deepen; $0, no LLM).
- `startd8 kickoff explain [--intro | --inputs | <domain>]` — what each input is and why we ask.
<!-- /TL;DR -->

---

## What "kickoff" is

Before the startd8 pipeline builds an application, it collects a defined set of **inputs** — the
things the build cannot invent: what the business wants to achieve, what "good" looks like in
numbers, what technology conventions to follow, what the operating budget is, and how the running
app should be watched. The kickoff is that collection step.

The guiding rule: **machines draft and translate; humans validate and decide.** Every input carries
a status (`authored` / `placeholder` / `absent`) and a provenance ("who supplied this — a human, a
default, an estimate?") so nothing that looks done is silently fake.

## Posture — pick how much ceremony you want

- **Prototype / dogfood** — one team plays all roles. **No humans are required to start**: every
  value ships pre-filled (industry defaults + drafted starters), adjusted at will. Deployment
  defaults to `installed` (single-user, local-first).
- **Production** — inputs come from named human roles; pre-filled drafts are there to react to, not
  to ship silently. Deployment defaults to `deployed` (multi-user, behind a gateway).

You choose the posture when you run `instantiate --posture …`; it seeds defaults and is never
forced. `guided` shows you the choice and its consequences before you commit.

## The recommended order

1. **`survey`** — see what the project already has (docs, models, fixtures, PII risk). Read-only.
2. **`assess`** — see readiness: which of the four input domains are present, and what gates block
   the $0 cascade. Read-only.
3. **`instantiate`** — materialize the input package: `KICKOFF_INTRO.md`,
   `KICKOFF_INPUTS_EXPLAINED.md`, and `inputs/{business-targets,observability,conventions,
   build-preferences}.yaml`, each pre-filled and never blank.
4. **Adjust the values**, flipping each to `provenance: authored` as a human decides it. Before any
   non-demo use, replace the deliberately-fictional **contacts/escalation** block in
   `observability.yaml`.
5. **Run the $0 cascade** (`startd8 generate backend|scaffold|views`) — most of the application is
   projected deterministically from the data-model contract at zero LLM cost.

## What kickoff does NOT ask for here

The **data-model contract** (`schema.prisma` — the single most important human-designed input), the
**assembly manifests** (`app.yaml`, `pages.yaml`, `views.yaml`, …), and **content prose** are
file-shaped inputs that live in the project itself; kickoff references them, it does not duplicate
them. See `startd8 kickoff explain --inputs` for the full "what we ask / why / who" of each domain,
and the per-project `KICKOFF_INPUTS_EXPLAINED.md` written by `instantiate`.

<!-- PLAIN -->
## Getting started — the plain version

You're about to set up a new app. Before the tool can build it, it needs to know a few things about
what you want — things it can't just guess. That's what "kickoff" is: a short setup step where you
answer (or accept our suggestions for) a handful of questions.

**You can't break anything here, and you can change any answer later.** Where you're not sure, we
fill in a safe, sensible default for you — so you're never stuck. Nothing is final until you say so.

Here's the whole idea in three steps:

1. **See what's there.** `startd8 kickoff assess` shows you what's set up and what still needs an
   answer. It only looks — it doesn't change anything.
2. **Set it up.** `startd8 kickoff instantiate` creates the setup files, already filled in with good
   starting values you can edit.
3. **Adjust what matters to you** and leave the rest — the safe defaults are fine to keep.

A few words you might see:

- **"input"** — one of the things the app needs to know (like your budget, or what the app is for).
- **"default"** — a value we picked for you so you don't have to. Always changeable.
- **"provenance"** — just a label showing where a value came from: *you typed it*, or *we suggested
  it*. It's there so nothing pretends to be finished when it isn't.

When you're ready, run `startd8 kickoff assess` to see where you stand. Take it one answer at a time.
<!-- /PLAIN -->

