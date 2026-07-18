# Architect — Role Kit

> **The first docs-first role kit** (the seed that fuels FR-KIT / `startd8 kit`). Grounded in
> `HITM_ROLE_MODEL_REQUIREMENTS.md` §3.3 + FR-J9 (the completeness triad). A kit is **complete**
> when it names (a) a draft template, (b) a review checklist, and (c) the role's validation
> artifact — all three below, each pointing at a *real* pipeline artifact (never restated — cited).

**Role:** Architect · **Tier:** U/E (the *choice* + contract design) over G (LLM-draftable options)
**Mission (HITM §3.3):** requirements → **technical architecture** — persistence + display
frameworks, the convention manifest, the contract (schema), and the architecture decision records.
**Where in the flow:** the **DATA MODEL front bookend** — the first human validation point, before
any cascade run.

## The FR-J9 completeness triad

| Slot | Artifact | Home |
|---|---|---|
| **(a) draft template** | convention manifest + contract + ADR skeleton | [`draft-template.md`](./draft-template.md) |
| **(b) review checklist** | the architecture review (CRP-grounded) | [`review-checklist.md`](./review-checklist.md) |
| **(c) validation artifact** | the **convention manifest + contract**, approved at the DATA MODEL bookend | [`validation.md`](./validation.md) |
| **(c+) the visualization layer** *(how (c) is made glance-approvable)* | wireframe → descriptive layer → node navigator; + the visualization layer's own acceptance test | [`validation-visualization.md`](./validation-visualization.md) |

## Anti-fork (FR-KIT-4)
This kit is a **view over** the canonical artifacts; it does not fork them. Each slot **cites** its
source (the wireframe CLI, the CRP guide, the convention/contract schemas) — a future `startd8 kit
architect` renders these pointers, it does not copy their content. If a cited source moves, fix the
pointer here; never duplicate.

## Completeness self-check
- [x] (a) draft template named + linked
- [x] (b) review checklist named + linked
- [x] (c) validation artifact named + linked (the DATA MODEL bookend approval)

*Kit status: **complete** (3/3). This is 1 of 11 delivery-role kits — the seed; the other 10 are
unauthored (the real open loop behind FR-KIT).*
