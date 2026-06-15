# <Project> — Plan

> **TEMPLATE** — copy into `<project>/docs/`, replace every `<…>`, delete guidance (`▷`) lines
> and this banner. How-to:
> [`HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md`](HOW_TO_AUTHOR_REQUIREMENTS_AND_PLANS.md).
> Worked reference instance: `strtd8/docs/kickoff/PLAN_v3.0-draft.md`.

**Version:** <1.0>   **Date:** <YYYY-MM-DD>
**Pairs with:** `<REQUIREMENTS file>`
**Format:** requirements-and-plan-format v0.1

## Overview

<2–4 sentences: how the build proceeds, bottom-up.>

## Iterations

▷ Three iterations, fixed meaning: ① the data + storage foundation, ② the screens and business
▷ logic on top of it, ③ the AI/outside-system integrations last. Most of ①–② is assembled
▷ deterministically from the data model — mark those rows "0 (deterministic)": no AI writes
▷ them and they cost nothing per run. Feature ids: F-1xx / F-2xx / F-3xx by iteration.

### Iteration 1 — framework + persistence
*Done when: <the schema is authored, the app compiles, the database creates, the app boots empty>.*

| Feature | FRs | Target files | Est. LOC |
|---------|-----|--------------|----------|
| F-101 <feature> | <FR-n, FR-m> | <paths> | <0 (deterministic) \| N> |

### Iteration 2 — display + business logic
*Done when: <CRUD round-trips, forms submit, views render — on placeholder/test data>.*

| Feature | FRs | Target files | Est. LOC |
|---------|-----|--------------|----------|
| F-201 <feature> | <FR-n> | <paths> | <…> |

### Iteration 3 — integration + content population
*Done when: <integrations produce correct-SHAPE output on test fixtures; the app degrades
gracefully when a key/system is absent>. Real user-facing content is the user's — never a
build deliverable.*

| Feature | FRs | Target files | Est. LOC |
|---------|-----|--------------|----------|
| F-301 <feature> | <FR-n> | <paths> | <…> |

## Dependencies

▷ AUTHOR these explicitly — one per line, "X after Y", no cycles. The build validates
▷ acyclicity; nothing here is ever inferred.
- F-201 after F-101
- <F-x after F-y>

## Budget & routing

Per `<project>/docs/kickoff/inputs/build-preferences.yaml` (referenced, not restated).

## The two human bookends (every iteration)

- **Front — data-model checkpoint:** does the contract carry what this iteration needs?
  (The wireframe walkthrough is this checkpoint's artifact.)
- **Back — retrospective:** did the increment fulfil intent; what feeds back into the data
  model / requirements / this plan?
