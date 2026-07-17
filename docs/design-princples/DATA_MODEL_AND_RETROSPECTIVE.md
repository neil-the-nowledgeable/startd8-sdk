# Data Model & Retrospective — The Two Human Bookends

Purpose: name where human leverage concentrates as implementation automates. When the pipeline can
deterministically build ~89% of an application (bucket 1) and LLM-generate the integration glue
(bucket 3), the human's highest-value work is not in the middle — it is at the two ends: **designing
the contract the machine derives from** (front), and **reflecting on what the increment actually
produced and feeding that back** (back). This document is intentionally living guidance. Update it
as the automated middle grows and the bookends sharpen.

---

## The Principle

> As implementation automates, human leverage does not disappear — it **concentrates at the two
> bookends of every increment**:
>
> - **DATA MODEL (front bookend)** — designing the contract (`schema.prisma`) that the deterministic
>   cascade projects into a working app. This is the one input the pipeline **must never author**.
> - **RETROSPECTIVE (back bookend)** — reflecting on what the increment *actually* built (the code,
>   the run, the disk — not the plan) and feeding the lessons back into the data model, the
>   requirements, and the plan before the next pass.
>
> **Bracket every `cap-dev-pipe` pass with both.** The machine owns the middle; the human owns the
> ends.

The middle — scaffolding, CRUD, forms, views, integration wiring — is exactly the work the SDK has
made cheap or free. Pouring human attention there is a form of [Zero Value
Precision](./ZERO_VALUE_PRECISION_ANTI_PRINCIPLE.md). The scarce, non-automatable judgment lives at
the ends.

---

## Why This Matters

The SDK's whole thesis is that most of an application is *determined* once the contract exists (see
[Hitsuzen](./HITSUZEN_DESIGN_PRINCIPLE.md)): one `schema.prisma` projects deterministically into
models, tables, CRUD, HTMX UI, pages, and views at **$0 LLM cost** (bucket 1, the
`backend_codegen` cascade). If the middle is derived, then the quality of the whole output is
bounded almost entirely by **two human acts**:

1. **The contract you hand the machine.** A vague, wrong, or placeholder `schema.prisma` produces a
   vague, wrong, or placeholder app — faithfully and for free. Determinism amplifies the front
   bookend: garbage-in is now garbage-out *at scale and at speed*.
2. **What you learn from each pass and route back.** A cascade run is cheap enough to do many times.
   The value of that cheapness is only realized if each run's actuals sharpen the next run's inputs.
   A retrospective that never reaches the data model is a lesson discarded — see
   [Kaizen](./KAIZEN_DESIGN_PRINCIPLE.md).

Between these two acts, the human's marginal contribution approaches zero. Outside them, it
approaches everything.

### The front bookend: DATA MODEL

The contract (`schema.prisma`, the Prisma IDL — not the YAML manifests around it) is the front
bookend. Design it **before** the first cascade run. Concretely, per
[`KICKOFF_REQUIREMENTS.md`](../design/KICKOFF_REQUIREMENTS.md) **FR-F3** (bookend bracketing) and
**FR-F2** (provisioning status):

- The pipeline **records** the contract; it **never authors** it. A missing or scaffold-stub
  `schema.prisma` is `placeholder`/`absent`, never `authored`.
- Reference scale: the `strtd8` reference contract is ~15 entities. That is the shape of a real
  front bookend — real entities, fields, and relations — not a TODO-marked stub.
- Everything downstream is a projection of this one artifact. The
  [bucket separation](../../CLAUDE.md) is precise about this: bucket 1 (application) *derives from*
  the contract; the determinism story describes bucket 1 only.

### The back bookend: RETROSPECTIVE

After each increment, reflect on the **actuals** — the generated code, the run logs, the disk
state, the post-mortem — and feed findings back into the data model, requirements, and plan. This
is [Hansei](./HANSEI_DESIGN_PRINCIPLE.md) applied at the increment boundary: reflect on what
happened, extract what it proved, and spread it (*yokoten*). The retrospective is the mechanism by
which a cheap, repeatable cascade *compounds* instead of merely *repeating*
([Ichigo Ichie](./ICHIGO_ICHIE_DESIGN_PRINCIPLE.md) keeps each run's quality high; the retrospective
makes the *next* run's inputs better).

The direction of flow matters: retrospective findings flow **back to the front** — into the data
model and the requirements — not merely into a fix applied to this increment's output. A lesson that
only patches the current artifact, without updating the contract that will regenerate it, will be
re-learned every pass.

---

## Relationship to the Principle Family

| Principle | How the bookends relate |
|-----------|-------------------------|
| **[Hitsuzen](./HITSUZEN_DESIGN_PRINCIPLE.md)** | Determinism is *why* the middle collapses and leverage moves to the ends. The more the pipeline derives, the sharper the bookends must be. |
| **[Hansei](./HANSEI_DESIGN_PRINCIPLE.md)** | The back bookend **is** Hansei at the increment boundary — reflect on actuals, standardize the gain. |
| **[Kaizen](./KAIZEN_DESIGN_PRINCIPLE.md)** | The retrospective is the human, per-increment expression of Kaizen; findings must reach the data model or the lesson is discarded. |
| **[Zero Value Precision](./ZERO_VALUE_PRECISION_ANTI_PRINCIPLE.md)** | Spending human effort in the automated middle is the anti-pattern this principle steers away from. |
| **[Sotto](./SOTTO_DESIGN_PRINCIPLE.md)** | Authored content (bucket 4) rides the deterministic skeleton without disturbing it — a *content* seam, distinct from the *contract* bookend. |

---

## Where This Is Operationalized

- **CLAUDE.md — "Generation Scope & Priority"** frames the bucket separation and names these two
  bookends as the human leverage points bracketing every `cap-dev-pipe` pass.
- **[`HITM_ROLE_MODEL_REQUIREMENTS.md`](../design/HITM_ROLE_MODEL_REQUIREMENTS.md)** generalizes the
  two bookends into a full human-in-the-machine role map (adds the missing U-tier owner and Security
  roles, dispositions, and a `draft-rejected` state).
- **[`KICKOFF_REQUIREMENTS.md`](../design/KICKOFF_REQUIREMENTS.md)** FR-F2/FR-F3 make the front
  bookend a machine-checkable provisioning state and direct collection toward both bookends.
- **[`kickoff/KICKOFF_ASSEMBLY_INPUTS.md`](../design/kickoff/KICKOFF_ASSEMBLY_INPUTS.md)** and
  **[`kickoff/ASSEMBLY_INPUTS_TEMPLATE.md`](../design/kickoff/ASSEMBLY_INPUTS_TEMPLATE.md)** mark
  `schema.prisma` as the front bookend in the assembly-input inventory.

---

*A note on scope: this is a principle about **human process**, not a code capability. It has no
module. Its enforcement surfaces are the kickoff/collection requirements (front) and the
retrospective/Hansei workflow (back) — the pipeline records what the human decides; it does not
decide for them.*
