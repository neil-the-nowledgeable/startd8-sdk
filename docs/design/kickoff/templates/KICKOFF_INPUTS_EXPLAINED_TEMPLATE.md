# <Project> — Kickoff Inputs, Explained (what we ask for, and why)

> **TEMPLATE** — instantiate per project (see `../KICKOFF_INPUT_PACKAGE_GUIDE.md`). Replace
> `<…>`, adapt the §1 metric names to the product, delete this banner.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**Status:** Active
**Audience:** Business-focused — written so a non-engineer stakeholder can read it cold.
**Companion:** `KICKOFF_INTRO.md` (the process), `inputs/*.yaml` (the values).

> Every section answers: **What are we asking for? Why does the build need it? Who provides it?**

---

## 1. Business targets — *what does success look like, in numbers?*

**File:** `inputs/business-targets.yaml`
**What we ask:** measurable goals — <the product's core funnel rate>, <success rate of its key
artifact/action>, expected usage, acceptable cost per <unit of value>, and (when monetized)
conversion and price points.
**Why:** the app ships with dashboards on day one; without targets they show *activity* with no
notion of *good*. Targets become goal lines and thresholds, declared before the measuring
instruments exist, so first real data lands against a stated expectation.
**Who:** the business/product owner — these are decisions, not facts. *(Pre-filled with
LLM-drafted starters, marked `estimate`.)* **Too early to commit numbers?** That's normal and
supported: keep a target as `TBD` (dormant) or leave the starter as an estimate — the system
tracks it as awaiting a decision and never treats it as a failure. Declaring *what* you'll
measure matters now; the number can come when there's data.

## 2. Observability — *how will we know the app is healthy, and who hears when it isn't?*

**File:** `inputs/observability.yaml`
**What we ask:** how available the app should be, how fast pages should respond, when cost or
errors should page somebody, where alerts go, who is on call, and the bones of an incident
playbook.
**Why:** the pipeline generates monitoring artifacts *with* the application; alerts with no real
destination and runbooks with no owner look done but are decorative. These are exactly the
inputs that can't be derived from code — commitments and contacts.
**Who:** the operations owner + business owner. *(Pre-filled from the matching industry default
dataset, marked `config-default`; contacts ship fictional and MUST be replaced before non-demo
use.)*

## 3. Technology conventions — *what stack and structure must everything follow?*

**File:** `inputs/conventions.yaml`
**What we ask:** framework, data layer, template engine, module layout, naming, implementation
language — one page of "this is how code looks here."
**Why:** the highest-leverage page in the package. When generation doesn't *know* the
conventions, it **invents** them (real incident: a generator produced Flask where the project
used FastAPI, purely because nothing said otherwise). A declared sheet, injected into every
generation tier, is the difference between code that drops in and code that needs rework.
**Who:** the architect — in the production model this sheet is generated from the project's own
plan/requirements by the pipeline, then architect-validated.

## 4. Build preferences — *how should the factory itself run?*

**File:** `inputs/build-preferences.yaml`
**What we ask:** spend ceilings per pipeline run and per month, AI model tiers per difficulty of
work, the implementation language, the generation profile.
**Why:** the pipeline spends real money per run; unstated budgets mean silent overspend or a
surprise mid-run stop. Declaring ceilings — and recording chosen-vs-defaulted — keeps the
economics as visible as product health.
**Who:** the project manager / budget owner. **Prototype/PoC shortcut:** if the project
declared traffic profile `test` or `internal`, a coherent **non-production default set**
applies (per-run/monthly ceilings, local-only deployment, standard model tiers — see the file's
defaults table) — no budget decisions are required to start; defaults stay visibly marked as
defaults until you change one.

## 5. The inputs we do NOT ask for here (already in the project)

The file-shaped kickoff inputs live in the project and are inventoried in
<path to ASSEMBLY_INPUTS.md>: the **data-model contract** (the single most important
human-designed input — most of the application derives from it deterministically at $0 LLM
cost), the **assembly manifests**, and **content prose** (placeholder by design; real
user-facing words are LLM-drafted strictly for acceptance sessions and become real only on human
approval).

---

| Domain | File | Normally from | This project's posture |
|--------|------|---------------|------------------------|
| Business targets | `inputs/business-targets.yaml` | business/product owner | <estimate / authored> |
| Observability | `inputs/observability.yaml` | ops + business owner | <config-default; contacts fictional> |
| Conventions | `inputs/conventions.yaml` | architect | <generated+validated / authored> |
| Build preferences | `inputs/build-preferences.yaml` | PM / budget owner | <estimate / authored> |
| Contract + manifests + content | <ASSEMBLY_INPUTS.md path> | architect + team | <status> |
