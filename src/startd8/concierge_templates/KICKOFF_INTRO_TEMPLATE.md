# <Project> — Kickoff Process Intro

> **TEMPLATE** — instantiate per project (see `../KICKOFF_INPUT_PACKAGE_GUIDE.md`). Replace
> `<…>`, pick ONE posture in §2, delete this banner.

**Version:** 0.1
**Date:** <YYYY-MM-DD>
**Status:** Active
**Audience:** Project team + stakeholders. Plain-language first.
**Companions:** `KICKOFF_INPUTS_EXPLAINED.md` (what each input is and why we ask),
`inputs/*.yaml` (the values, one file per domain), <project business docs to converge with>.

---

## 1. What "kickoff" is

Before the startd8 pipeline builds an application, it collects a defined set of **inputs** — the
things the build genuinely needs and cannot invent: what the business wants to achieve, what
"good" looks like in numbers, what technology conventions to follow, what the operating budget
is, and how the running app should be watched. The kickoff is that collection step.

Machines draft and translate; humans validate and decide. Every input is tracked with a status
(`authored` / `placeholder` / `absent`) and a provenance ("who supplied this — a human, a
default, an estimate?") so the build is always honest about what's real.

## 2. This project's posture  *(pick one, delete the other)*

**Production:** inputs come from named human roles — <Customer/PO name> states goals, the
business analyst maintains requirements, the architect validates conventions, <ops owner>
supplies real contacts and alert destinations. Pre-filled drafts are provided everywhere to
react to, never to silently ship: a human decision flips each value to `authored`. *Deployment
default:* production seeds `deployment.mode: deployed` (multi-user, shared DB, behind a gateway)
— unless this is a desktop/CLI tool, which legitimately stays `installed`. You always decide.

**Prototype/dogfood:** the <team name> team plays all roles (solo mode). **No humans are
required to start** — every value ships pre-filled (industry defaults + LLM-drafted starters),
adjusted at will. Provenance still records which decisions await a real owner. *Deployment
default:* prototype seeds `deployment.mode: installed` (single-user, local-first). See
`KICKOFF_INPUTS_EXPLAINED.md` → "Deployment posture" for the `deploy:` block when you go live.

## 3. What's in this package

| File | What it holds |
|------|---------------|
| `KICKOFF_INPUTS_EXPLAINED.md` | Business-language description of every input domain |
| `inputs/business-targets.yaml` | Goals-in-numbers: KPI targets, traction, unit economics |
| `inputs/observability.yaml` | Uptime/latency targets, alert thresholds, contacts, runbook |
| `inputs/conventions.yaml` | Technology conventions the build must follow |
| `inputs/build-preferences.yaml` | Spend ceilings, model tiers, language, profile |

**Not duplicated here:** the data-model contract, assembly manifests, and content prose are
working files inventoried in <path to project ASSEMBLY_INPUTS.md>; this package references,
never copies.

## 4. How to use it

1. Read `KICKOFF_INPUTS_EXPLAINED.md` once.
2. Skim `inputs/*.yaml` — every value is usable as-is.
3. Adjust freely; on change, set that value's `provenance:` to `authored`.
4. Converge starters toward real decisions as the business docs firm up.
5. Before any non-demo use: replace the **contacts/escalation** block in `observability.yaml`
   (it ships deliberately fictional).
