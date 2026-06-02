# Convergent Review Prompt

**Generated:** 2026-06-02 03:30:43 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)** — initializing the Appendix A/B/C scaffold if the doc has none yet (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`). The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 12 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deterministic-frontend/DETERMINISTIC_FRONTEND_GENERATION_PLAN.md` | 212 lines · 1589 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deterministic-frontend/DETERMINISTIC_FRONTEND_GENERATION_REQUIREMENTS.md` | 242 lines · 2263 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deterministic-frontend/CRP_FOCUS.md` | 58 lines · 551 words |

Treat the embedded documents below as **read-only ground truth** for this review. If something conflicts between plan and requirements, call it out explicitly in suggestions and in the coverage mapping.

---

## Your Task

You are a **senior architectural reviewer** with **file-edit tools** (Write/Edit/equivalent) and filesystem access to the source documents listed above. Your job is to produce **improvement suggestions** (structured, anchored, actionable) and **persist them directly into the source documents** by appending a new **Review Round** under each reviewed document's **Appendix C (Incoming)** — see **Prior Review State** below.

**First, read the existing review state** (Appendix A/B/C) in each source doc and **avoid re-proposing** what is already settled (A) or rejected (B), and **avoid near-duplicates** of untriaged items in C (dedup rules below). If a doc has **no** review-log appendix yet, **initialize the A/B/C scaffold** at the end of that doc (additive only) before appending your round.

**Do not** triage (no ACCEPT/REJECT disposition for your own or others' suggestions — that is orchestrator-side and lands in Appendix A/B), **do not** modify or rewrite existing prose, **do not** alter Appendix A/B or **prior rounds** in Appendix C, and **do not** emit a numbered suggestion list in chat — the orchestrator reads them from the files.

Optimize for **actionable, mergeable feedback** written into the right file.

### Prior Review State — read this BEFORE writing suggestions

Each source document **is** the persistent review state. Before proposing anything, parse its `## Appendix: Iterative Review Log` (if present):

- **Appendix A (Applied / Accepted)** — settled improvements. **Do not re-propose** anything here.
- **Appendix B (Rejected)** — read each **rationale**. Do **not** re-propose a rejected idea unless you explicitly cite its ID and argue why the rationale no longer holds.
- **Appendix C (Incoming)** — prior rounds, some untriaged. **Do not duplicate** a near-identical suggestion; if you agree with an untriaged item, **endorse** it (see Deliverables) instead of restating it.

**Your round number** is `R{n}` where **n = (highest existing `#### Review Round R{n}` in Appendix C) + 1**, or **1** if none exist. Put it in every suggestion ID: **R{n}-S{k}** (plan) / **R{n}-F{k}** (requirements).

**Go deeper, not wider:** prior reviewers caught the obvious issues — look for what they missed (second-order effects, cross-cutting concerns, interactions between already-accepted suggestions), and spend effort on areas with **few accepted** suggestions rather than those already **substantially addressed** (3+ accepted).

### Mode: Dual-Document Review

You have been given **two documents**: a project plan and a feature requirements document. Use **dual-document** perspective (plan ↔ requirements consistency) to inform your **suggestions only**—do not run full CRP phase/triage automation in this chat.

- Generate **S-prefix** suggestions targeting the **plan** (gaps, sequencing, risks, interfaces, validation strategy).
- Generate **F-prefix** suggestions targeting the **requirements** (ambiguity, missing acceptance criteria, inconsistencies, untestable statements).
- Optionally include a **Requirements coverage** table (each major requirement ID or section → plan section/task → **Covered / Partial / Gap**) as *observations* to inform the orchestrator—still **suggestions / analysis**, not triage.
- Use suggestion IDs so the orchestrator can map items to plan vs requirements later.

**Dual-document quality bar:** At least **three** F-prefix suggestions must cite a **specific sentence or table row** in the requirements; at least **three** S-prefix suggestions must cite a **specific section or task ID** in the plan. **Deprioritize** generic suggestions without anchors.


### Configuration (for structuring your suggestions)

| Parameter | Value |
|-----------|-------|
| Max suggestions (soft cap) | 12 |
| Review areas to consider | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |

### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

# CRP Focus — Deterministic Frontend Generation

Where we most need independent review input. Weight suggestions toward these. Prefer
**anchored, actionable, testable** items over generic architecture commentary.

## 1. Robustness (the renderer must not silently mis-render the schema)
The whole thesis ("invention impossible by construction") collapses if the Prisma→Zod
renderer mishandles a schema construct and emits wrong-but-plausible output. Stress the
**Prisma surface area** the plan's `SCALAR_MAP`/`FieldSpec` must cover and the failure mode
for each:
- Arrays (`String[]`, `Int[]`), enums (`enum Role {…}` → `z.enum([...])`), `@map`/`@@map`
  (DB-name vs field-name divergence), native types (`@db.VarChar`), `@default`, `@updatedAt`,
  composite types (`type` blocks), `Unsupported(...)`, `Bytes`, `Decimal`.
- Relations: 1-1, 1-n, implicit m-n, **self-relations**, relation scalar FKs (`authorId` IS a
  scalar that must be rendered; the relation `author` must be excluded — does the plan
  distinguish the FK scalar from the relation object?).
- Optionality vs nullability vs default vs list — `String?` → `.nullable()` but what about
  `String[]?`, or a field with `@default` (still required in Zod?).
- **Failure policy:** the plan says unknown type → `UnsupportedPrismaTypeError`. Is hard-fail
  right, or should it be a recorded "unrenderable field → fall back to a flagged regen item"
  so one exotic field doesn't block generating the other 11 correct models? Argue the tradeoff.

## 2. Value to the end user (the prime-contractor operator)
- Beyond killing RUN-011: what makes this *usable*? CLI ergonomics, the manifest, the diff
  report. Is `startd8 generate frontend` the right surface, or should it be a
  `plan-ingestion`/forward-manifest hook from day one?
- **Drift detection as a standalone win:** even before pipeline ownership (deferred Inc 9), a
  `--check` mode that compares the generated output against the on-disk (LLM-authored) file and
  reports divergence would deliver value immediately and turn `prisma_zod_symmetry` into a
  CI gate on real runs. Worth pulling forward?
- Does the owned/seeded split (FR-7) actually help the operator, or add ceremony? Where's the
  minimal version that still prevents the inventions?

## 3. Functional & architectural quick wins / low-hanging fruit
- What can we get nearly free by reusing `observability/artifact_generator` /
  `dashboard_creator/generator` patterns (manifest shape, emission, provenance)?
- `z.infer<typeof XSchema>` TS-type emission (FR OQ-1) — is it actually a 1-line follow-on
  worth shipping in v1 rather than deferring?
- Enum rendering and the directory-skeleton-from-manifest (RUN-013 fix) — are these smaller
  than they look and worth folding into Inc 5 rather than Inc 7?
- Is there a cheaper proof than the full strtd8 acceptance harness (Inc 5) for an earlier
  signal?

## 4. Operational enhancements
- Regeneration-on-schema-change: how is staleness detected (schema hash in the GENERATED
  header? a `--check` that exits non-zero in CI?).
- Telemetry: should the generator emit OTel spans/metrics (models rendered, fields,
  unrenderable count) consistent with the SDK's observability conventions?
- How does this compose operationally with repair-retry and Approach A — ordering, and who
  runs first in a real pipeline run?
- Idempotence/ownership enforcement: how do we *detect* an LLM (or human) editing an `owned`
  GENERATED file (the drift FR-4/NFR-4 worries about) without the deferred pipeline seam?

## 5. Sequencing / scope sanity
- Is renderer-first (Inc 1–5 before convention detection) the right order, or does FR-5
  convention detection need to come first so the renderer knows the project's alias/conventions?
- Anything in v1 scope that should be deferred, or deferred (Inc 9) that's actually cheap
  enough to pull in?

**If the focus file above contains numbered asks** (e.g. `A1`/`A2`/`Ask 1`/`Ask 2` or similar), address each ask **at the top of your appended appendix**, before standard S/F-prefix suggestions, using this template per ask (orchestrator triages later — **no** ACCEPT/REJECT tables here, and **no** chat-only response):

```
- **Summary answer:** one sentence (e.g. yes / no / partial / depends on X)
- **Rationale:** 2–4 sentences with citations to FR-IDs, plan sections, or headings
- **Assumptions / conditions:** what must hold for your answer; or "none"
- **Suggested improvements:** concrete doc or plan deltas (bullet list OK)
```

Standard CRP S/F-prefix suggestions are **secondary** when explicit asks are present; do not let area-coverage steering distort effort allocation.

---

### Reviewer contract — suggestion quality and anti-slop rules

Every **suggestion you list** should be written so the orchestrator could **merge it as-is** if they agree (their adopt/decline step is **not** your task here). Aim for:

1. **Actionable** — A human could turn it into an edit, a new task, or a test without further clarification meetings.
2. **Anchored** — Include a **verbatim fragment** (short quote) or **heading path** from the document under review so the author can find the locus quickly.
3. **Scoped** — One primary issue per suggestion; use multiple suggestions instead of bundling unrelated concerns.
4. **Testable when relevant** — For requirements changes, state **how** acceptance could be verified (criterion, automated check, or explicit manual step).

**Reviewer attribution:** use your model identifier exactly as you would self-identify (e.g., `claude-opus-4-7-1m`, `claude-sonnet-4-6`, `claude-haiku-4-5`, `gpt-5`). Do not invent.

**Length budget:** target roughly **500–1500 words** total across the appended appendix sections (adjust up slightly if the focus file has many numbered asks). Quality over volume.

**Self-filter (do not label as triage):** Omit vague praise (“looks good”), duplicate issues, and purely stylistic nits unless they block comprehension. **Also omit near-duplicates of suggestions already in Appendix A/B/C** — endorse or extend the existing ID instead (see Deliverables). If something **contradicts stated project constraints**, frame it as a **scope trade-off** suggestion rather than as a mandate.

**Deliverables (mandatory — persist to source files, not chat):**

1. **Append a `#### Review Round R{n} — <your-model-id> — <UTC date>`** block under **Appendix C (Incoming)** of each source document you reviewed (plan suggestions → plan file; requirements suggestions → requirements file). If a doc has no `## Appendix: Iterative Review Log`, **initialize the A/B/C scaffold** at its end first (additive only). Use Write/Edit; do **not** modify existing prose, Appendix A/B, or prior rounds.
2. **Inside your round block**, include:
   - **Executive summary** — at most **10 bullets**: top risks, opportunities, blocking gaps (no triage tables).
   - **Numbered suggestions** — full list with **R{n}-S{k}** / **R{n}-F{k}** IDs. Optional "first pass" / "adversarial pass" subsections — **no** ACCEPT/REJECT columns.
3. **Endorsements & Disagreements (do this if you have tokens remaining):** after your suggestions, react to **untriaged** prior items (in Appendix C, not yet in A/B):
   - `**Endorsements**` — prior IDs you agree with, one-line reason each.
   - `**Disagreements**` — untriaged prior IDs you would reject, one-line reason (so triage can weigh it).
   This builds the cross-model consensus signal the orchestrator uses during triage.
4. **(Dual mode only)** Append a `## Requirements Coverage Matrix — R{n}` section at the **end of the plan file** mapping each major requirement ID/section → plan section/task → **Covered / Partial / Gap**. Analysis only.
5. **Chat reply** — a **short write-confirmation** (1-3 lines) with your round number, file paths, and counts (e.g. `Round R2: 6 S-suggestions → plan.md, 4 F → requirements.md, 3 endorsements`). **Do not** repeat suggestion content in chat.

**Suggestion ID reminder (dual mode):** Plan → **R{n}-S{k}**; Requirements → **R{n}-F{k}** (n = your round, computed from Appendix C; the orchestrator triages your items into Appendix A/B afterward).

### Optional second-pass suggestions (inside the appended appendix, still no triage)

If you still have budget under the max-suggestions cap after your first list, you may add a `### Stress-test / adversarial pass` subheading **inside your round block**, with **additional** numbered suggestions (continue **R{n}-S\*** / **R{n}-F\*** numbering within the same round — do not fabricate a separate round). Try to break your own prior conclusions where it genuinely helps; skip if redundant. **Still no in-chat list** — keep the chat reply to the short write-confirmation.


---

### Pre-flight (before drafting suggestions)

1. **Optionally expand** the protocol guide `<details>` block below and skim **quality norms** (anchoring, scope, security). You are **not** executing full CRP phase/triage automation—use the guide as reference only.
2. Read the **Document Under Review** section(s) once for structure; read again while drafting suggestions.
3. Note **explicit out-of-scope** lines — do not file suggestions that only restate excluded work unless you flag a **dependency risk** (why exclusion threatens delivery).

---

### Protocol guide — optional reference (norms for good suggestions)

**Important:** Some chat clients or models collapse `<details>` by default. Expand if you need **deeper** CRP vocabulary; this prompt does **not** require you to run guide phases 5–7 (triage, appendix merge, final document emit).

If anything in the guide seems to conflict with **this prompt’s “suggestions only” scope**, **this prompt wins** for what you must deliver in-chat; the orchestrator reconciles with the guide afterward.


### Scope lock (normative — overrides conflicting text in the guide below)

The long **Protocol guide** block below (wrapped in an HTML **details** element) embeds the **full** CRP guide, including instructions for **triage**, **appendix edits**, and **document rewrites**. For **this** assignment:

**You MUST:**

- First **read** each source doc's Appendix A/B/C and **avoid re-proposing** settled (A) or rejected (B) items; **dedup** against untriaged C.
- Use file-edit tools to **append a `#### Review Round R{n}` block** under **Appendix C** of each reviewed doc, computing **n** = highest existing round + 1 (or 1). If no `## Appendix: Iterative Review Log` exists, **initialize the empty A/B/C scaffold** (additive) first.
- In dual mode, also append a `## Requirements Coverage Matrix — R{n}` section to the end of the plan file.
- If tokens remain, add an **Endorsements & Disagreements** block on untriaged prior suggestions.

**You MUST NOT:**

- Triage (no ACCEPT/REJECT disposition for your own or others' suggestions) — that is orchestrator-side and lands in Appendix A/B.
- Modify, rewrite, reorder, or delete existing prose, **populated** Appendix A/B, or **prior rounds** in Appendix C. (Creating the empty scaffold when none exists is allowed.)
- Execute **Phase 5–7** (triage/merge) from the guide, or output a **rewritten** document body.
- Reproduce the full numbered suggestion list in chat — chat output is a **short write-confirmation** only.

Treat the guide as **optional reference** for vocabulary, risk lenses, and quality norms only — not as a second execution checklist.

## Convergent Review Protocol — Agent Execution Guide

<details>
<summary><strong>Expand: full CRP protocol guide</strong> (you append your round to Appendix C; triage into Appendix A/B is orchestrator-side)</summary>

# Convergent Review Protocol (CRP) — Agent Execution Guide

**Purpose:** Step-by-step instructions for any AI agent to run the Convergent Review Protocol on a document. Covers first-encounter initialization, document formatting, review rounds, triage, and convergence tracking.

**Protocol source:** `ARCHITECTURAL_REVIEW_REQUIREMENTS.md` (76 requirements, RV-100 through RV-807)

---

## How This Process Works: Multi-Agent Iterative Review

**You are not the only reviewer.** This document undergoes multiple sequential review rounds, each performed by a different agent (or the same agent in a later pass). The CRP is designed so that each reviewer builds on the cumulative work of all prior reviewers — not by re-reading their raw suggestions, but by reading the **triaged outcomes** persisted in the document itself.

### What You Inherit From Prior Reviewers

When you receive a document that has already been through CRP rounds, the appendix structure contains the full review history:

- **Appendix A (Applied)** — Suggestions that prior reviewers proposed and that were accepted during triage. These are the "settled" improvements. **Do not re-propose anything that already appears here.**
- **Appendix B (Rejected)** — Suggestions that were explicitly rejected with rationale. **Read the rejection rationale carefully.** If you believe a rejected idea should be reconsidered, you must explicitly reference its ID and argue why the original rationale no longer applies. Do not silently re-propose rejected ideas.
- **Appendix C (Incoming)** — Raw suggestion tables from each prior round, plus any endorsement blocks. Contains both triaged and untriaged suggestions. Your job is to add a new round here, not modify existing rounds.
- **Areas Substantially Addressed / Areas Needing Further Review** — Coverage tracking sections that tell you which areas have enough accepted suggestions and which still need attention.

### Your Role as Reviewer R{n}

Each review pass should be **sharper than the last**. You are not starting from scratch — you are working from the foundation laid by R1 through R{n-1}. Your job is to:

1. **Go deeper, not wider** — Prior reviewers handled the obvious issues. Look for what they missed: second-order effects, unstated assumptions, cross-cutting concerns, and interactions between already-accepted suggestions.
2. **Challenge, don't repeat** — If prior rounds covered an area well, do not generate more suggestions in that area unless you find a genuine gap. Redundant suggestions waste triage effort.
3. **Endorse good untriaged work** — If a prior reviewer proposed something valuable that hasn't been triaged yet, endorse it rather than proposing a duplicate. Endorsements build consensus signal.
4. **Respect rejections** — Rejected suggestions were dismissed for a reason. Read the rationale. Only revisit if circumstances have changed or the rationale was flawed.

### The Document Is the State

There is no external database or API tracking review state. The document's appendix structure **is** the persistent state. Round numbers, applied/rejected decisions, coverage counts, and endorsement signals are all derived by parsing the document. This means:

- If the document is passed to you with Appendices A/B/C populated, prior rounds happened.
- If Appendix A is empty and Appendix C has no rounds, you are the first reviewer.
- If coverage sections show 5 of 7 areas addressed, the review is in its middle-to-late phase.
- Your output is appended to the document and becomes part of the state for the next reviewer.

---

## Quick Reference

| Concept | Value |
|---------|-------|
| Review areas | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |
| Severities | critical, high, medium, low |
| Suggestion ID format | `R{round}-S{n}` (plan), `R{round}-F{n}` (feature requirements) |
| Table columns (7) | ID, Area, Severity, Suggestion, Rationale, Proposed Placement, Validation Approach |
| Substantially addressed threshold | 3 accepted suggestions per area (configurable) |
| Appendix A | Applied suggestions (accepted and integrated) |
| Appendix B | Rejected suggestions (with rationale) |
| Appendix C | Incoming suggestions (untriaged, append-only) |

---

## Phase 0: First-Encounter Initialization

When you receive a document for review **for the first time** (no appendix structure exists), you must prepare it before generating any review suggestions.

### Step 0a: Detect Whether Initialization Is Needed

Search the document for this heading:

```
## Appendix: Iterative Review Log (Applied / Rejected Suggestions)
```

- **If found:** The document has been through CRP before. Skip to Phase 1.
- **If not found:** This is a first encounter. Continue with Step 0b.

### Step 0b: Append the Appendix Structure

Append the following template **verbatim** to the end of the document, separated from the body by a horizontal rule (`---`):

```markdown
---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
```

### Step 0c: Save the Initialized Document

Write the document back with the appendix appended. **Do not modify the document body.** The initialization is purely additive.

---

## Phase 1: Pre-Review Analysis

Before generating suggestions, analyze the current state of the document.

### Step 1a: Parse Existing State

1. **Scan Appendix A** — collect all applied suggestion IDs and their areas.
2. **Scan Appendix B** — collect all rejected suggestion IDs. Read rejection rationale to understand what has already been considered and dismissed.
3. **Scan Appendix C** — find the highest existing round number by searching for `#### Review Round R{n}` headings. Your round number is `max(existing) + 1`, or `1` if no rounds exist.
4. **Collect untriaged suggestions** — any suggestions in Appendix C whose IDs do not appear in Appendix A or B.

### Step 1b: Compute Area Coverage

For each of the 7 review areas, count how many suggestions have been **accepted** (appear in Appendix A):

| Area | Accepted Count | Addressed? (>= 3) | Gap |
|------|---------------|-------------------|-----|
| Architecture | ? | ? | ? |
| Interfaces | ? | ? | ? |
| Data | ? | ? | ? |
| Risks | ? | ? | ? |
| Validation | ? | ? | ? |
| Ops | ? | ? | ? |
| Security | ? | ? | ? |

An area is **substantially addressed** when it has >= 3 accepted suggestions (the default threshold; configurable per run).

#### Understanding "Substantially Addressed"

This threshold is a **steering mechanism**, not a quality certification. An area with 3 accepted suggestions is not "done" — it means the review process has invested enough attention there that additional suggestions in that area should only come from genuine insight, not routine scanning. The threshold exists to prevent late-round reviewers from piling more suggestions into areas that are already well-covered while neglecting areas with zero coverage.

**How it affects your behavior:**

| Coverage State | Your Priority | What to Do |
|----------------|--------------|------------|
| 0 accepted in an area | Highest | This area has been completely overlooked. Allocate suggestion slots here first. |
| 1–2 accepted in an area | High | Below threshold. Prioritize but check what's already accepted to avoid overlap. |
| 3+ accepted in an area | Low | Substantially addressed. Only propose if you find something the prior 3+ suggestions genuinely missed. |
| All 7 areas at 3+ | Shift focus | Enter gap-hunting mode. Stop thinking in terms of individual areas and look for cross-cutting concerns, low-hanging opportunities, and design principle alignment. |

**Key insight:** The coverage table in Step 1b is your primary decision tool for allocating review effort. Do not distribute suggestions evenly across areas — concentrate on the gaps.

### Step 1c: Determine Review Mode

Based on coverage analysis:

- **Some areas below threshold** — Enter **two-tier priority mode** (Phase 2a). Focus your suggestion slots on uncovered areas.
- **All areas at or above threshold** — Enter **gap-hunting and opportunity mode** (Phase 2b). Shift from area coverage to deeper analysis, cross-cutting concerns, and high-value opportunities.
- **Most areas addressed (5–6 of 7)** — Use two-tier mode but recognize you are in a late-phase review. For the 1–2 remaining gaps, be precise. For addressed areas, consider whether the plan/requirements create natural opportunities for low-effort, high-value improvements (see Phase 2b, Lens 1).

---

## Phase 2a: Two-Tier Priority Review

When uncovered areas exist, structure your review to prioritize them.

### Tier 1: Priority Areas (uncovered)

List each area below the substantially addressed threshold. For each:
- Note how many accepted suggestions it has
- Note the gap (threshold minus count)
- Allocate **at least `max_suggestions - 1`** of your suggestion slots to these areas

### Tier 2: Addressed Areas (secondary)

For areas already substantially addressed:
- Only propose suggestions if you find a **genuine gap** that the existing accepted suggestions missed
- Do not rehash topics already well-covered
- Consider whether accepted suggestions in addressed areas **enable low-effort extensions** — if so, these belong in your Tier 2 slots (see Phase 2b, Lens 1)

### Transitional State (5–6 of 7 areas addressed)

When only 1–2 areas remain below threshold, you are in a **transitional state** between two-tier and gap-hunting modes. Handle this by:

1. Allocating 2–3 suggestion slots to the remaining uncovered areas (Tier 1)
2. Using the rest of your slots for gap-hunting and opportunity suggestions across the already-addressed areas (Tier 2, using the Phase 2b lenses)
3. Paying special attention to interactions between the uncovered area(s) and the well-covered areas — these cross-cutting blind spots are the most common late-phase misses

### Generate Your Suggestions

Produce a review round following the output format in Phase 3.

---

## Phase 2b: Gap-Hunting and Opportunity Mode

When all 7 areas are substantially addressed (or nearly so — 5–6 of 7 with the remainder close), shift from area coverage to deeper analysis and value discovery.

**Mindset shift:** In early rounds, reviewers are scanning for problems — missing sections, unaddressed risks, gaps in coverage. By the time all areas are substantially addressed, the obvious problems have been found. Your job now is different: find what the plan/requirements **make possible but don't yet exploit**, and surface cross-cutting issues that only become visible after the foundational suggestions are in place.

### Gap-Hunting and Opportunity Lenses

Evaluate the document through these lenses, in order of priority:

**1. Low-hanging fruit: high-value improvements enabled by the plan**

The most valuable late-round suggestions are often not about what's *wrong* but what's *almost there*. Read the plan and requirements together and ask: given what is already committed to, what low-effort additions would deliver outsized value?

- **Capabilities that are 80% built** — The plan describes infrastructure (an event bus, a validation layer, an API gateway) that could serve additional use cases with minimal extension. Call these out specifically: "Since you are already building X, adding Y is ~N lines of additional work and enables Z."
- **Data already flowing that isn't being captured** — The plan may route data through a pipeline without persisting intermediate results that would be valuable for debugging, analytics, or audit. If the data is already in hand, storing it is low effort.
- **Configuration that could be externalized** — Hard-coded values, thresholds, or feature flags mentioned in the plan that could be made configurable with minimal overhead, enabling runtime tuning without redeployment.
- **Reusable building blocks** — A component built for one task that could serve 2–3 other tasks if its interface were slightly generalized. The plan already pays the cost of building it — generalizing it captures compound value.
- **Test infrastructure synergies** — Test fixtures, mock services, or validation harnesses described for one feature that could be shared across features with minor refactoring.

**Framing:** These suggestions should emphasize the **effort-to-value ratio**. "Since the plan already does A, extending it to also do B requires [specific low effort] and yields [specific high value]." Avoid vague "it would be nice" suggestions — quantify the lift and the payoff where possible.

**2. Gaps and cross-cutting concerns**
- Contradictions between areas (e.g., an ops process that conflicts with an architecture decision)
- Assumptions that were never validated
- Second-order effects of accepted suggestions — do any of the previously accepted changes create new risks or interactions?
- Edge cases or failure modes not yet addressed
- Interactions between accepted suggestions from different rounds that were reviewed independently

**3. Missed opportunities to leverage platform capabilities**
- Data or artifacts already available from upstream pipeline stages that the design ignores
- Deterministic computations being deferred to stochastic LLM inference
- Existing infrastructure (OTel, ContextCore contracts, capability index) that could replace hand-rolled solutions
- Reusable components or shared utilities that would reduce duplication

**4. Design principle violations**

Evaluate against these three principles:

- **Mottainai** (waste aversion) — Are artifacts from earlier pipeline stages being discarded or regenerated instead of forwarded? Is deterministic data being re-derived via LLM? Does the design inventory what exists before generating?

- **Context Correctness by Construction** (declare-and-verify) — Does the design declare what context must flow between phases and verify it at boundaries? Are there silent degradation paths where missing context falls through to defaults without signaling? Are contracts prescriptive (declare and verify) rather than descriptive (collect and hope)?

- **Context Contracts** (boundary validation) — Do phase boundaries validate required fields with appropriate severity (BLOCKING/WARNING/ADVISORY)? Is provenance tracked so data can be traced to its source? Can the design degrade gracefully when upstream data is missing rather than failing silently?

### Prioritizing Late-Round Suggestions

When you are in gap-hunting and opportunity mode, prioritize your suggestion slots in this order:

1. **Low-effort, high-value opportunities** (Lens 1) — These are the most actionable and most likely to be accepted during triage because they build on decisions already made.
2. **Cross-cutting gaps** (Lens 2) — Issues that span multiple areas are the ones most likely to have been missed by area-focused early rounds.
3. **Platform leverage** (Lens 3) — Concrete opportunities to replace custom work with existing infrastructure.
4. **Principle violations** (Lens 4) — Important but more abstract; triage may defer these if the other suggestions are more immediately actionable.

---

## Phase 3: Generate the Review Round

### Output Format (strict)

Your output must be **only** an appendable markdown snippet. Do not rewrite the document. Do not modify Appendix A or Appendix B.

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {brief description of review focus}

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-S1 | {area} | {severity} | {suggestion text} | {why this matters} | {where in the doc} | {how to verify} |
| R{n}-S2 | ... | ... | ... | ... | ... | ... |
```

### Output Rules

1. **Round heading** — Must be `#### Review Round R{n}` with the correct round number.
2. **Metadata block** — Must include Reviewer, Date (UTC), and Scope.
3. **Table columns** — Must use exactly these 7 headers: `ID`, `Area`, `Severity`, `Suggestion`, `Rationale`, `Proposed Placement`, `Validation Approach`. Plain text headers only (no bold, no italic).
4. **Suggestion IDs** — Must follow `R{round}-S{n}` format, numbered sequentially starting at 1.
5. **Area values** — Must be one of: `Architecture`, `Interfaces`, `Data`, `Risks`, `Validation`, `Ops`, `Security`. Use title case.
6. **Severity values** — Must be one of: `critical`, `high`, `medium`, `low`. Use lowercase.
7. **Suggestion count** — At least 1, at most 10 (configurable; default 10).
8. **Pipe escaping** — If suggestion text contains `|`, escape it as `\|` to preserve table structure.
9. **No appendix modification** — Output must NOT contain `### Appendix A` or `### Appendix B` headings.
10. **No document rewriting** — Output the snippet only, not the entire document.

### Endorsements (optional)

If you agree with untriaged suggestions from prior rounds (in Appendix C but NOT in Appendix A or B), append an endorsement block after your table:

```markdown
**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R{prior_round}-S{n}: {one-sentence reason you agree}
- R{prior_round}-S{m}: {one-sentence reason you agree}
```

Only endorse suggestions you genuinely believe should be implemented. Do not endorse your own suggestions from the current round.

---

## Phase 4: Append the Review Round

Append your generated snippet to the end of the document, after all existing content in Appendix C. Do not insert it anywhere else.

---

## Phase 5: Triage

After all review rounds for this session are complete, triage all untriaged suggestions.

### Step 5a: Collect Untriaged Suggestions

Parse Appendix C for all suggestion rows whose IDs do **not** appear in Appendix A or Appendix B.

### Step 5b: Classify Each Suggestion

For each untriaged suggestion, decide:

- **ACCEPT** — The suggestion is valuable and should be integrated into the document. Move a row into Appendix A.
- **REJECT** — The suggestion is not worth implementing. Move a row into Appendix B **with a specific rationale** explaining why.

Consider endorsement counts: suggestions endorsed by multiple reviewers across rounds carry stronger consensus signal.

### Step 5c: Route Decisions to Appendices

**For ACCEPT decisions**, insert a row into Appendix A:

```markdown
| R{n}-S{m} | {suggestion summary} | {source reviewer} | {implementation/validation notes} | {YYYY-MM-DD} |
```

**For REJECT decisions**, insert a row into Appendix B:

```markdown
| R{n}-S{m} | {suggestion summary} | {source reviewer} | {specific rejection rationale} | {YYYY-MM-DD} |
```

Replace the `(none yet)` placeholder rows when inserting the first real entry.

### Step 5d: Partial Triage Is Acceptable

You do not need to triage every suggestion in a single pass. Suggestions not covered remain untriaged in Appendix C for the next triage pass.

---

## Phase 6: Update Coverage Sections

After triage, update (or insert) two coverage tracking sections in the document. These go **inside** the appendix, before Appendix A.

### Step 6a: Areas Substantially Addressed

Insert or update this section:

```markdown
### Areas Substantially Addressed

- **Architecture**: {count} suggestions applied ({id1}, {id2}, ...)
- **Interfaces**: {count} suggestions applied ({id1}, {id2}, ...)
- ...
```

Only list areas that have reached the threshold (>= 3 accepted).

### Step 6b: Areas Needing Further Review

Insert or update this section (after "Areas Substantially Addressed"):

```markdown
### Areas Needing Further Review

- **Data**: {count}/{threshold} suggestions accepted (need {gap} more)
- **Security**: {count}/{threshold} suggestions accepted (need {gap} more)
- ...
```

Only list areas below the threshold.

---

## Phase 7: Verify Protocol Invariants

Before finishing, verify these invariants hold:

1. **Append-only** — Appendix C content from prior rounds was not modified. Only new rounds were appended.
2. **Monotonic rounds** — Your round number is strictly greater than all existing round numbers.
3. **No body modification** — The document body (everything before the appendix `---` separator) was not changed by the review process (only by explicit triage-driven integration, if applicable).
4. **Domain exhaustiveness** — All 7 review areas were considered during your review. None were skipped.
5. **ID uniqueness** — Your suggestion IDs do not collide with any existing IDs in the document.

---

## Dual-Document Mode: Plan + Requirements Combo Evaluation

When you are given both a **plan document** and a **feature requirements document**, you operate in dual-document mode. This mode adds requirements traceability, a second suggestion stream, and cross-document routing on top of the standard CRP phases.

### When to Enter Dual-Document Mode

Enter dual-document mode when **both** of these are true:

1. You have a plan/design document (the primary review target)
2. You have a separate feature requirements document that the plan is supposed to implement

If you only have a plan with no separate requirements doc, use standard single-document mode (Phases 0–7 above).

### Quick Reference (Dual-Document Additions)

| Concept | Value |
|---------|-------|
| Plan suggestion IDs | `R{n}-S1`, `R{n}-S2`, ... (S-prefix) |
| Requirements suggestion IDs | `R{n}-F1`, `R{n}-F2`, ... (F-prefix) |
| Extra output section | `#### Feature Requirements Suggestions` table |
| Extra output section | `#### Requirements Coverage` mapping table |
| Routing | S-prefix → plan doc appendices; F-prefix → requirements doc appendices |

---

### Phase 0-DD: Initialize Both Documents

Both documents must have the three-appendix structure. Run Phase 0 (Steps 0a–0c) independently on **each** document:

1. **Plan document** — check for `## Appendix: Iterative Review Log` heading. If missing, append the full appendix template (Phase 0b).
2. **Requirements document** — check for the same heading. If missing, append the same appendix template.

Both documents are now ready for CRP review rounds.

---

### Phase 1-DD: Pre-Review Analysis (Both Documents)

Extend Phase 1 to cover both documents:

1. **Parse plan document state** — Appendix A/B/C, round number, coverage (same as Phase 1a–1c).
2. **Parse requirements document state** — Appendix A/B/C of the requirements doc. Track accepted/rejected F-prefix IDs separately.
3. **Read the requirements document body** — identify each requirement section/heading. You will need these for the coverage mapping.

### Phase 2-DD: Review With Traceability

Your review must cover three concerns simultaneously:

1. **Plan quality** — the same 7-area architectural review (Phases 2a/2b apply as normal). These produce S-prefix suggestions targeting the plan document.
2. **Requirements quality** — are the requirements themselves ambiguous, conflicting, incomplete, or missing acceptance criteria? These produce F-prefix suggestions targeting the requirements document.
3. **Plan-to-requirements traceability** — does the plan adequately address every requirement? This produces the Requirements Coverage table.

---

### Phase 3-DD: Generate the Review Round (Dual-Document Output)

Your output must contain **three sections** in this order:

#### Section 1: Plan Suggestions (S-prefix)

The standard 7-column table, identical to single-document mode:

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {brief description of review focus}

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-S1 | {area} | {severity} | {plan suggestion} | {why} | {where in plan} | {how to verify} |
| R{n}-S2 | ... | ... | ... | ... | ... | ... |
```

**Rules:** Same as Phase 3 output rules (7 columns, area/severity enums, max 10 S-prefix suggestions per round).

#### Section 2: Feature Requirements Suggestions (F-prefix)

A **separate** table under its own heading for issues found in the requirements document itself:

```markdown
#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R{n}-F1 | {area} | {severity} | {requirements issue} | {why} | {where in requirements doc} | {how to verify} |
| R{n}-F2 | ... | ... | ... | ... | ... | ... |
```

**When to generate F-prefix suggestions:**

- A requirement is **ambiguous** — could be interpreted multiple ways by an implementer
- A requirement is **conflicting** — contradicts another requirement or a plan decision
- A requirement is **incomplete** — missing acceptance criteria, boundary conditions, or error cases
- A requirement is **missing** — the plan reveals a need that no requirement covers
- A requirement is **untestable** — no clear way to verify it was implemented correctly

**If the requirements are clean**, you may omit this section entirely (or include it with zero rows). Do not invent issues.

#### Section 3: Requirements Coverage Mapping

A traceability table mapping each requirement section to plan coverage:

```markdown
#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| {requirement heading or ID} | {plan section(s) that address it} | Full | — |
| {requirement heading or ID} | {plan section(s) that address it} | Partial | {what's missing from the plan} |
| {requirement heading or ID} | (none) | Missing | {the plan does not address this requirement} |
```

**Coverage values:**

| Value | Meaning |
|-------|---------|
| `Full` | The plan fully addresses this requirement with clear implementation steps |
| `Partial` | The plan mentions it but is missing detail, edge cases, or implementation specifics |
| `Missing` | The plan does not address this requirement at all |

**Rules:**

- Every requirement section in the requirements document must appear in this table. Do not skip any.
- When Coverage is `Partial` or `Missing`, the Gaps column must explain specifically what is lacking.
- `Partial` coverage with gaps should generate a corresponding S-prefix suggestion in Section 1 (proposing the plan addition).
- `Missing` coverage should generate a corresponding S-prefix suggestion in Section 1 (proposing plan coverage for the requirement).

---

### Phase 4-DD: Append and Route

After generating your output:

1. **Plan suggestions (S-prefix)** — Append the full round snippet (Section 1 + Section 3) to the **plan document's** Appendix C.
2. **Feature suggestions (F-prefix)** — If Section 2 is non-empty, wrap it in a round heading with metadata and append it to the **requirements document's** Appendix C:

```markdown
#### Review Round R{n}

- **Reviewer**: {your name or model identifier}
- **Date**: {YYYY-MM-DD HH:MM:SS UTC}
- **Scope**: {scope} (Feature Requirements)

#### Feature Requirements Suggestions
{the F-prefix table from Section 2}
```

**Do not mix S-prefix and F-prefix suggestions in the same document's appendix.**

---

### Phase 5-DD: Triage (Both Documents)

Triage handles both prefixes:

1. **Collect all untriaged suggestions** — S-prefix from the plan doc's Appendix C, F-prefix from the requirements doc's Appendix C.
2. **Classify each suggestion** — ACCEPT or REJECT, same as Phase 5.
3. **Route decisions by prefix:**
   - S-prefix ACCEPT → plan document Appendix A
   - S-prefix REJECT → plan document Appendix B
   - F-prefix ACCEPT → requirements document Appendix A
   - F-prefix REJECT → requirements document Appendix B

---

### Phase 6-DD: Update Coverage (Both Documents)

Update the "Areas Substantially Addressed" and "Areas Needing Further Review" sections in **both** documents independently, based on each document's own Appendix A counts.

---

### Phase 7-DD: Verify Invariants (Both Documents)

Verify all Phase 7 invariants on **both** documents:

- Append-only, monotonic rounds, no body modification, domain exhaustiveness, ID uniqueness
- **Additional invariant:** No S-prefix IDs in the requirements document's appendix; no F-prefix IDs in the plan document's appendix

---

### Worked Example: First Dual-Document Review

**Scenario:** You receive `IMPLEMENTATION_PLAN.md` and `FEATURE_REQUIREMENTS.md`, neither has appendix structure.

#### 1. Initialize Both

Append the appendix template to both documents (Phase 0-DD).

#### 2. Analyze

- Plan: empty appendices, Round 1, all areas at 0/3
- Requirements: empty appendices
- Requirements doc body has 5 sections: Authentication, Rate Limiting, Data Export, Audit Logging, Error Handling

#### 3. Generate Round R1

**Section 1 (Plan suggestions):**

```markdown
#### Review Round R1

- **Reviewer**: Claude Opus 4.6 (claude-opus-4-6)
- **Date**: 2026-02-28 20:00:00 UTC
- **Scope**: Full architectural review with requirements traceability

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add rate limiting middleware layer | Plan has no rate limiting implementation despite REQ-RL-001 | Section 3: API Design | Load test with rate limit thresholds |
| R1-S2 | Security | critical | Add JWT token rotation strategy | Authentication section lacks token lifecycle management | Section 2: Authentication | Security audit of token flow |
| R1-S3 | Data | medium | Define data export pagination | Export endpoint will timeout on large datasets | Section 4: Data Export | Test export with 100k+ records |
| R1-S4 | Ops | high | Add structured audit log format | Audit logging requirement has no log schema in plan | Section 5: Audit Logging | Verify log entries match schema |
```

**Section 2 (Requirements suggestions):**

```markdown
#### Feature Requirements Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | medium | Add rate limit thresholds to REQ-RL-001 | Requirement says "rate limiting" but specifies no limits (requests/sec, burst) | Rate Limiting section | Verify numeric thresholds are specified |
| R1-F2 | Interfaces | medium | Add error response format to Error Handling | Requirement specifies "graceful error handling" but no response schema | Error Handling section | Verify JSON error schema is defined |
```

**Section 3 (Coverage mapping):**

```markdown
#### Requirements Coverage

| Requirement Section | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| Authentication | Section 2: Authentication | Partial | Missing token rotation and session management |
| Rate Limiting | (none) | Missing | No rate limiting section in the plan |
| Data Export | Section 4: Data Export | Partial | No pagination or timeout strategy |
| Audit Logging | Section 5: Observability | Partial | Mentioned but no structured log format |
| Error Handling | Section 6: Error Handling | Full | — |
```

#### 4. Route

- Append the full snippet (Sections 1 + 3) to `IMPLEMENTATION_PLAN.md` Appendix C
- Wrap Section 2 in a round heading and append to `FEATURE_REQUIREMENTS.md` Appendix C

#### 5. Triage

- Accept R1-S1, R1-S2, R1-S4 → plan Appendix A
- Reject R1-S3 (pagination is handled by framework) → plan Appendix B
- Accept R1-F1 → requirements Appendix A
- Accept R1-F2 → requirements Appendix A

#### 6. Update Coverage

Plan: Architecture=1, Security=1, Ops=1 — all below threshold. Requirements: track F-prefix accepted counts separately.

---

## Area Aliases

LLMs sometimes use synonyms for area names. Normalize them:

| Synonym | Canonical Area |
|---------|---------------|
| design, structure, modularity, scalability, maintainability, extensibility, clarity, readability, documentation | Architecture |
| api, apis, contracts, integration | Interfaces |
| data model, data models, storage, database, persistence | Data |
| risk, reliability, resilience, fault tolerance, error handling | Risks |
| testing, testability, test, quality, completeness | Validation |
| operations, deployment, observability, monitoring, performance, infrastructure | Ops |
| auth, authentication, authorization | Security |

---

## Column Aliases

LLMs sometimes use different column headers. Normalize them:

| Synonym | Canonical Column |
|---------|-----------------|
| #, No, No., Number, Item, Ref, Suggestion ID | ID |
| Category, Domain, Focus Area, Topic | Area |
| Level, Priority, Impact, Sev | Severity |
| Recommendation, Finding, Issue, Description, Detail, Details | Suggestion |
| Reasoning, Justification, Reason, Explanation, Why | Rationale |
| Placement, Location, File, File Path, Where | Proposed Placement |
| Validation, Test, Testing, How to Validate, Verification | Validation Approach |

---

## Worked Example: First Review of a New Document

**Scenario:** You receive `IMPLEMENTATION_PLAN.md` with no appendix structure.

### 1. Initialize

Detect: no `## Appendix: Iterative Review Log` heading found. Append the full appendix template (Phase 0b).

### 2. Analyze

- Appendix A: empty (no applied suggestions)
- Appendix B: empty (no rejected suggestions)
- Appendix C: empty (no prior rounds)
- Round number: 1 (no existing rounds)
- Coverage: all areas at 0/3, all below threshold

### 3. Review (Two-Tier Priority)

All 7 areas are uncovered, so all are Tier 1 priority. Generate up to 10 suggestions spread across the areas with the largest gaps.

### 4. Output

```markdown
#### Review Round R1

- **Reviewer**: Claude Opus 4.6 (claude-opus-4-6)
- **Date**: 2026-02-28 18:00:00 UTC
- **Scope**: Full architectural review — initial pass across all 7 areas

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Add dependency injection for service layer | Improves testability and decouples components | Section 3: Architecture | Unit test coverage of isolated services |
| R1-S2 | Security | critical | Add input validation at API boundary | Prevents injection attacks (OWASP A03) | Section 5: API Design | OWASP ZAP scan + fuzz testing |
| R1-S3 | Data | medium | Define schema migration strategy | Avoids breaking changes on deployment | Section 4: Data Model | Dry-run migration against staging DB |
| R1-S4 | Risks | high | Add circuit breaker for external API calls | Prevents cascade failures under load | Section 6: Integration | Load test with upstream service unavailable |
| R1-S5 | Validation | medium | Add contract tests for API consumers | Catches breaking changes before deployment | Section 5: API Design | Run contract test suite in CI |
| R1-S6 | Ops | high | Define health check endpoints | Required for orchestrator liveness probes | Section 7: Deployment | Verify probe responses under load |
| R1-S7 | Interfaces | medium | Version the REST API from day one | Avoids breaking consumers on iteration | Section 5: API Design | Integration test with versioned routes |
```

### 5. Append

Append the snippet after `### Appendix C: Incoming Suggestions (Untriaged, append-only)`.

### 6. Triage

Evaluate each suggestion. For this example, accept R1-S1 through R1-S4 and reject none:

Insert into Appendix A:
```markdown
| R1-S1 | Add dependency injection for service layer | Claude Opus 4.6 | Restructured service layer with DI container | 2026-02-28 |
| R1-S2 | Add input validation at API boundary | Claude Opus 4.6 | Added Pydantic validators on all endpoints | 2026-02-28 |
| R1-S3 | Define schema migration strategy | Claude Opus 4.6 | Added Alembic migration section to data model | 2026-02-28 |
| R1-S4 | Add circuit breaker for external API calls | Claude Opus 4.6 | Added resilience section with circuit breaker pattern | 2026-02-28 |
```

### 7. Update Coverage

After triage, compute new coverage and insert sections:

```markdown
### Areas Substantially Addressed

(No areas have reached the threshold of 3 accepted suggestions yet.)

### Areas Needing Further Review

- **Architecture**: 1/3 suggestions accepted (need 2 more)
- **Interfaces**: 0/3 suggestions accepted (need 3 more)
- **Data**: 1/3 suggestions accepted (need 2 more)
- **Risks**: 1/3 suggestions accepted (need 2 more)
- **Validation**: 0/3 suggestions accepted (need 3 more)
- **Ops**: 0/3 suggestions accepted (need 3 more)
- **Security**: 1/3 suggestions accepted (need 2 more)
```

### 8. Next Round

The next reviewer (Round R2) will see the applied IDs (R1-S1 through R1-S4), the untriaged suggestions (R1-S5 through R1-S7), and the coverage gaps. They will prioritize areas with the largest gaps (Interfaces, Validation, Ops) and may endorse untriaged suggestions from Round 1.

---

## Convergence Criteria

The review process converges naturally as areas cross the substantially addressed threshold. Each phase has a distinct character:

### Phase Progression

| Phase | Typical Rounds | Coverage State | Reviewer Focus | Suggestion Character |
|-------|---------------|----------------|----------------|---------------------|
| **Early** | R1–R2 | 0–2 areas addressed | Broad scanning across all 7 areas | Foundational: missing sections, unaddressed risks, structural gaps |
| **Middle** | R2–R3 | 3–5 areas addressed | Two-tier priority steering toward remaining gaps | Targeted: filling specific coverage gaps, building on prior accepted work |
| **Late** | R3–R5 | 6–7 areas addressed | Gap-hunting + opportunity discovery | Refined: cross-cutting concerns, low-hanging fruit, high-value extensions |
| **Converged** | R5+ | All areas addressed, diminishing returns | Consider stopping | If fewer than 2–3 novel suggestions emerge, the document has likely converged |

### How to Tell Where You Are

When you receive a document for review, the coverage state tells you which phase the review is in:

- **Empty Appendix A + no prior rounds** — You are the first reviewer (early phase). Cast a wide net.
- **Some applied IDs, some areas still at 0** — Middle phase. Prior reviewers started the work but significant gaps remain. Be targeted.
- **Most or all areas at threshold, with untriaged suggestions pending** — Late phase. Prior reviewers covered the breadth. Your value-add is depth: cross-cutting issues, interactions between accepted suggestions, and opportunities that only become visible once the foundation is laid.
- **All areas addressed, few untriaged suggestions, and prior gap-hunting rounds exist** — The document may be converged. Only generate a round if you find genuinely novel insights. It is acceptable to produce a round with fewer than the maximum suggestion count, or to note that the document appears well-converged.

### Convergence Signals

The review is likely converged when:

1. All 7 areas are substantially addressed (3+ accepted suggestions each)
2. Gap-hunting rounds produce fewer than 2–3 novel suggestions
3. New suggestions are increasingly low-severity (medium/low) rather than high/critical
4. Endorsements outnumber new suggestions (reviewers agree with existing untriaged work rather than finding new issues)
5. The Requirements Coverage table (in dual-document mode) shows Full coverage across all requirement sections

### When Not to Stop

Even if coverage looks complete, continue if:

- Accepted suggestions from different rounds have **interactions that haven't been examined** (e.g., a caching strategy from R1 and a consistency requirement from R3 that may conflict)
- The plan describes infrastructure that **enables valuable extensions** not yet proposed (Lens 1 — low-hanging fruit)
- Rejection rationale in Appendix B reveals **recurring themes** suggesting a deeper architectural issue that individual suggestions have been working around rather than addressing directly

There is no fixed number of rounds required. A typical run uses 2–5 review rounds, but complex documents with many requirements may warrant more.

</details>

---

## Document Under Review: Project Plan

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deterministic-frontend/DETERMINISTIC_FRONTEND_GENERATION_PLAN.md`  ·  **Size:** 212 lines · 1589 words

```markdown
# Deterministic Frontend Generation — Implementation Plan

**Version:** 1.0 (pairs with `DETERMINISTIC_FRONTEND_GENERATION_REQUIREMENTS.md` v0.2)
**Date:** 2026-06-02
**Status:** Draft for review

> Build the one missing primitive — a **Prisma→Zod/TS renderer** — validate it with the
> existing `prisma_zod_symmetry` checker *by construction* (FR-3), prove it on the real
> strtd8 schema (FR-9), then layer convention-detection + the gated skeleton generators on
> top. Reuse `prisma_parser`, `scaffold_*`, `generate_tsconfig/dependency_file`; the renderer
> is the only net-new code. No LLM anywhere.

---

## 0. Strategy & sequencing

```
Inc 1  Field model + scalar/optionality mapping        (FR-1, FR-2)   — pure, the core
Inc 2  Convention layer (format hints, relation excl.) (FR-2)         — pure rules
Inc 3  Renderer → value-model.ts text + GENERATED hdr  (FR-1, FR-4)   — emit
Inc 4  Symmetry-by-construction gate                   (FR-3)         — wire prisma_zod_symmetry
Inc 5  strtd8 acceptance gate (real schema, 12 models) (FR-9)         — headline proof
Inc 6  Project-convention detection                    (FR-5)         — tsconfig + file scan
Inc 7  Gated skeleton generators (barrels/css/config)  (FR-6, FR-7)   — reuse scaffold_*
Inc 8  Owned/seeded manifest + CLI                     (FR-7, FR-8A)  — wiring
Inc 9  [deferred] pipeline ownership seam              (FR-8C)        — prime-contractor
```

Inc 1–5 deliver the headline (RUN-011 killed by construction, proven on real data). Inc 6–8
generalize to the rest of the mechanical surface. Inc 9 (pipeline ownership) is explicitly
deferred per FR-8/Non-Req v1.

**Module home (OQ-6 → resolve):** new `src/startd8/frontend_codegen/` package
(`schema_renderer.py`, `conventions.py`, `skeleton.py`, `manifest.py`), called by both the CLI
and (later) the prime-contractor. Sits beside `languages/` (reuses `prisma_parser`,
`nodejs`) and `repair/retry/scaffold` — does not extend `languages/nodejs` (keeps the
frontend-app concern out of the language-profile abstraction).

---

## 1. Key seams (what exists, what's new)

| Seam | Location | Role |
|------|----------|------|
| Prisma parse | `languages/prisma_parser.parse_prisma_schema(text)` | **reuse** — gives models, `field_names`, scalar types, optionality, relations |
| Field-set grounding | `contractors/upstream_interface.render_prisma_field_sets` | **reuse model, not output** — it emits *prompt text*; the new renderer emits the *file* (share the parsed field model) |
| Symmetry check | `validators/prisma_zod_symmetry.check_prisma_zod_symmetry` | **reuse as the FR-3 gate** — generator output must return `[]` |
| Barrel / CSS stub | `repair/retry/scaffold.{scaffold_barrel,scaffold_cofile}` | **reuse** for FR-6 |
| Config gen | `languages/nodejs.{generate_dependency_file,generate_tsconfig}` | **reuse** for FR-6 |
| Export introspection | `contractors/upstream_interface.{extract_ts_exports,resolve_specifier_to_paths}` | **reuse** for FR-5 convention detection |
| Precedent | `observability/artifact_generator`, `dashboard_creator/generator` | pattern to mirror (deterministic file emission) |
| **NEW** | `frontend_codegen/schema_renderer.py` | the one missing primitive — `render_zod_schema(models, conventions) -> str` |

---

## 2. Inc 1 — Field model + scalar/optionality mapping (FR-1, FR-2)

**`frontend_codegen/schema_renderer.py`:**
- `parse_models(schema_text) -> list[ModelSpec]` — thin wrapper over `parse_prisma_schema`
  producing `ModelSpec{name, fields:[FieldSpec{name, prisma_type, optional, is_relation,
  is_id, attrs}]}`. (If `parse_prisma_schema` already yields this, adapt rather than re-parse.)
- `SCALAR_MAP: dict[str,str]` — `String→z.string()`, `Int→z.number().int()`,
  `Float→z.number()`, `Boolean→z.boolean()`, `DateTime→z.string().datetime()`,
  `Json→z.unknown()`, `BigInt→z.bigint()`, `Decimal→z.string()` (per the documented mapping).
- `render_field_base(field) -> str` — scalar type + `?`→`.nullable()`.

**Tests:** every scalar maps; `String?` → `.nullable()`; an unknown Prisma type raises a
clear `UnsupportedPrismaTypeError` (no silent `z.any()`).

## 3. Inc 2 — Convention layer (FR-2)

**`frontend_codegen/conventions.py`:**
- `FieldConventions` (declared default rule set, overridable): format hints by field-name
  regex (`^email$|Email$`→`.email()`, `Url$|Uri$`→`.url()`), `@id`→`z.string()`,
  relation-exclusion predicate, id/provenance handling.
- `apply_conventions(field, base) -> str` — layer hints onto the base type; **deterministic,
  pure**.

**Tests:** `email`→`.email()`; `avatarUrl`→`.url()`; a relation field → excluded (predicate
True); same field → identical output twice (determinism). Seed the default rule set from the
documented `value-model.ts` mapping; do **not** infer from the (LLM-authored) existing file
(OQ-2 resolution).

## 4. Inc 3 — Renderer + GENERATED header (FR-1, FR-4)

- `render_zod_schema(models, conventions) -> str` — per model:
  `export const <Model>Schema = z.object({ <field>: <type>, … });` + (optional)
  `export type <Model> = z.infer<typeof <Model>Schema>;` (OQ-1 follow-on, behind a flag).
- `GENERATED_HEADER` constant: `// GENERATED from prisma/schema.prisma — do not edit by
  hand; regenerate via \`startd8 generate frontend\`. Source of truth: the Prisma schema.`
- Idempotent: deterministic field/model ordering (schema order), stable formatting.

**Tests:** two renders byte-identical (FR-4); header present; a 2-model schema renders the
expected text; relation fields absent.

## 5. Inc 4 — Symmetry-by-construction gate (FR-3)

- Wire `check_prisma_zod_symmetry(rendered_text, schema_text)` into a renderer self-test
  helper `assert_symmetric(rendered, schema)` and a unit test that runs it on rendered output.
- **Negative test:** monkeypatch the renderer to drop a field → the symmetry gate **fails**
  (proves the gate actually guards, not a tautology).

**Tests:** rendered strtd8 output → `[]` violations; a deliberately broken render → caught.

## 6. Inc 5 — strtd8 acceptance gate (FR-9, headline)

**`tests/unit/frontend_codegen/test_strtd8_acceptance.py`:**
- Load the real strtd8 `prisma/schema.prisma` (12 models) — committed as a fixture (or read
  via a path env, skipif absent for CI portability).
- Render → assert per-model scalar-field-set equality vs the committed `lib/value-model.ts`
  (parse both, compare field names + optionality; relations excluded on both sides).
- Assert 0 `prisma_zod_symmetry` violations.
- Emit a diff report of *intentional* convention differences (format hints) — informational.
- Assert the RUN-011 invented names (`aiRefId`, `label`, `outcomeId`, `title`,
  `supportingEvidence`) are **not** in the output (structurally impossible).

**This is the proof:** the file the LLM got wrong in RUN-011 is now generated correct from the
schema, validated by the same checker that used to catch the LLM's drift.

## 7. Inc 6 — Project-convention detection (FR-5)

**`frontend_codegen/conventions.py` (extend):**
- `detect_project_conventions(project_root) -> ProjectConventions{alias, alias_root,
  uses_barrels, uses_css_modules, types_dir}` — read `tsconfig.json` `paths` for the alias
  (`@/*`→`./*`); scan for any `index.ts` re-export barrels (`extract_ts_exports`); scan for
  `*.module.css`; detect a top-level `types/` dir.
- Absence is first-class: `uses_barrels=False` is an explicit "do not generate / project does
  not use barrels" signal (the RUN-012 anti-invention).

**Tests:** against a strtd8 fixture → `alias=@/→./`, `uses_barrels=False`,
`uses_css_modules=False`; against a synthetic barrel-using fixture → `uses_barrels=True`.

## 8. Inc 7 — Gated skeleton generators (FR-6, FR-7)

**`frontend_codegen/skeleton.py`:**
- `generate_skeleton(plan_manifest, schema, conventions, out_dir) -> SkeletonResult` —
  - schema types (Inc 3) — always (owned);
  - barrels via `scaffold_barrel` — **only if** `conventions.uses_barrels` (FR-6 gate);
  - CSS stubs via `scaffold_cofile` — only if `uses_css_modules`;
  - `package.json`/`tsconfig` via `nodejs.generate_*` — if absent;
  - directory skeleton from the plan's file manifest (mkdir the canonical dirs — prevents
    RUN-013 sub-namespace invention);
  - route/page **seeded shells** (FR-7): imports + handler signature + a guarded body region.
- Each output tagged `owned` or `seeded` in the result.

**Tests:** barrel-using project → barrel emitted; strtd8 (no barrels) → none emitted, none
invented; route shell is `seeded` with a guarded body; the directory skeleton matches the
manifest.

## 9. Inc 8 — Manifest + CLI (FR-7, FR-8 Phase A)

**`frontend_codegen/manifest.py`:** `GenerationManifest` — lists each generated path with
`{path, ownership: owned|seeded, source: schema|scaffold|config|dir, regenerable: bool}`.

**`cli.py`:** new `generate` command group → `startd8 generate frontend --schema <path>
--out <dir> [--project <root>] [--types-only] [--emit-interfaces]`. Renders schema types
(always) + skeleton (if `--project` given for convention detection); writes the manifest;
prints owned/seeded summary. No LLM, no network.

**Tests:** CLI renders types to `--out`; `--types-only` skips skeleton; manifest written.

## 10. Inc 9 — [DEFERRED] pipeline ownership seam (FR-8 Phase C)

Out of scope for v1 (Non-Req). Sketch for OQ-3: a `provided_files` input to the
prime-contractor that (a) pre-writes owned files before generation, (b) excludes them from the
LLM feature set, (c) orders dependent features after them via the forward manifest. Resolve the
mechanics (manifest tag vs plan annotation) in a follow-up requirements pass.

---

## 11. Requirement → increment traceability

| FR | Increment |
|----|-----------|
| FR-1 renderer | Inc 1, 3 |
| FR-2 convention layer | Inc 1, 2 |
| FR-3 symmetry-by-construction | Inc 4 |
| FR-4 marker + idempotent | Inc 3 |
| FR-5 project-convention detection | Inc 6 |
| FR-6 gated skeletons | Inc 7 |
| FR-7 owned/seeded ownership | Inc 7, 8 |
| FR-8A CLI | Inc 8 |
| FR-8C pipeline seam | Inc 9 (deferred) |
| FR-9 strtd8 acceptance | Inc 5 |
| FR-10 no-LLM/idempotent | all (NFR-1, enforced by tests) |

## 12. Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| `parse_prisma_schema` doesn't expose optionality/relations cleanly | Inc 1 adapts/normalizes into `FieldSpec`; if a gap, extend the parser (it's ours) — verify in Inc 1 first. |
| Convention hints (email/url) diverge from the hand-authored file | FR-9 emits a **diff report**; intentional differences are reviewed, not silently accepted; the rule set is the single declared source. |
| Symmetry gate is tautological (renderer + checker share a bug) | Inc 4 negative test (broken render must be caught) proves the gate bites. |
| strtd8 schema not available in CI | Commit a schema fixture; `skipif` on the live-path variant. |
| Skeleton generation overwrites an LLM-authored file | FR-7 owned/seeded split + GENERATED header; owned files are inert to the LLM (Phase C enforces exclusion). |
| Scope creep into business logic | Non-Req fences `lib/ai/*`, route/page bodies as LLM-owned (seeded shells only). |
| `z.infer` interface emission drifts from Zod | Behind `--emit-interfaces` flag (OQ-1); default off in v1. |

## 13. Conventions checklist
- [ ] `get_logger(__name__)` in new modules.
- [ ] **No hardcoded model strings** (there is no LLM here — assert zero provider imports).
- [ ] Reuse `parse_prisma_schema`/`scaffold_*`/`generate_tsconfig`/`prisma_zod_symmetry` — don't re-implement.
- [ ] New files added to `test_logger_acquisition_policy.py` allowlist if using string logger names.
- [ ] `pytest tests/unit/frontend_codegen -q` green; `ruff`/`black`/`mypy` clean.
- [ ] CLI `generate frontend` documented in `--help` + a docs entry.

---

*Plan v1.0 — renderer-first (Inc 1–5 kill RUN-011 by construction and prove it on the real
strtd8 schema), then convention-detection + gated skeletons (Inc 6–8); pipeline ownership
deferred (Inc 9). The only net-new code is the renderer; everything else reuses an existing
primitive. Pairs with requirements v0.2. CRP review offered before Inc 1.*
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deterministic-frontend/DETERMINISTIC_FRONTEND_GENERATION_REQUIREMENTS.md`  ·  **Size:** 242 lines · 2263 words

```markdown
# Deterministic Frontend Generation — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-02
**Status:** Draft for review — pairs with `DETERMINISTIC_FRONTEND_GENERATION_PLAN.md`
**Grounding:** `DETERMINISTIC_FRONTEND_GENERATION_INVENTORY.md` (the capability audit that
served as the planning pass).
**Reuses (don't rebuild):** `languages/prisma_parser.parse_prisma_schema`,
`contractors/upstream_interface.{render_prisma_field_sets,extract_ts_exports,resolve_specifier_to_paths}`,
`repair/retry/scaffold.{scaffold_barrel,scaffold_cofile}`,
`languages/nodejs.{generate_dependency_file,generate_tsconfig}`,
`validators/prisma_zod_symmetry`.

> **What this is.** A pure-Python, **no-LLM** capability that *generates* the mechanical
> frontend artifacts the LLM keeps inventing wrong — starting with the **Prisma→Zod/TS
> schema renderer** — so those artifacts are **never generated wrong** (prevention by
> construction), and the LLM is reserved for the semantic work (business logic, UX). This
> is the structural fix all three postmortems named, realized as **generation** rather than
> injection (Approach A) or repair (repair-retry).

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 ("deterministically generate the mechanical frontend") and v0.2
> (after the capability inventory grounded it in the real strtd8 project + SDK primitives).
> Four corrections; none kill the thesis, but they sharpen scope and the ownership model.

| v0.1 Assumption | Grounding Discovery | Impact |
|-----------------|---------------------|--------|
| `lib/value-model.ts` is **100% derivable from the Prisma schema** | It's derivable from the schema **+ documented conventions**: format hints (`email`→`.email()`, `*Url`→`.url()`), provenance fields (`ownerId`/`source`/`confirmed`), relation exclusion, optionality. The schema alone doesn't encode `email`/`url`. | **FR-2 added:** a small, deterministic **convention layer** (seeded from the project's own documented mapping), not raw Prisma projection. Still no LLM — just schema + rules. |
| Generate deterministic files **and exclude them from LLM features** | That needs prime-contractor pipeline surgery (feature-list filtering, dependency ordering, "this file is provided"). The **renderer ships standalone first** (CLI + a "provided files" seam); pipeline integration is a later phase. | **Scope phased (FR-1 vs FR-8):** Phase A = renderer (kills RUN-011 standalone); Phase C = pipeline ownership integration. Don't couple the two. |
| `prisma_zod_symmetry` stays a validator on **LLM output** | With deterministic generation it becomes a **regression guard on the generator** — the renderer's output must pass it **by construction** (a self-test), not a post-hoc check on the model. | **FR-3:** the generator's output passing `prisma_zod_symmetry` is an **acceptance gate**, and the validator's role shifts from "catch LLM drift" to "prove the generator can't drift." |
| The skeleton generator covers **route/page shells** the same way | Route/page files are **boilerplate-with-logic** — a fully-generated shell the LLM must then edit creates an **ownership/drift conflict** (who owns the file?). Fully-mechanical files (types/barrels/css/config) have no such conflict. | **FR-7 added:** two ownership models — **owned** (deterministic, LLM never touches) vs **seeded** (a scaffold the LLM completes). Only *owned* files are generated outright. |
| strtd8 has barrels/CSS to mirror | strtd8 has **0 barrels and 0 CSS modules** — RUN-012's inventions don't even fit the project's conventions. The right deterministic answer is partly *"the project doesn't use these, so don't generate (or invent) them."* | **FR-5 added:** **project-convention detection** (from `tsconfig` + existing files) drives generation; "project doesn't use X" is an explicit signal that *prevents* the invention, not just fills it. |

**Resolved open questions:**
- **OQ-A → Phase the scope.** Ship the Prisma→Zod renderer first (smallest, kills RUN-011);
  defer pipeline ownership integration.
- **OQ-B → Generation follows the *project's* conventions, not LLM priors** (FR-5).

Remaining open questions: OQ-1…OQ-6 in §6.

---

## 1. Problem Statement & Gap Table

Three postmortems, three invention classes, one root cause: the LLM produces **mechanical
artifacts from training-distribution priors** instead of the project's reality. We have
attacked this with *injection* (Approach A: tell the LLM the truth) and *repair* (repair-retry:
fix it after). Both leave the LLM in the loop for artifacts that **don't need it.** The cheapest
fix is to **not ask the LLM to generate them at all.**

| Invention class | Postmortem | Mechanical? | Today | Deterministic generation |
|-----------------|-----------|:-----------:|-------|--------------------------|
| Prisma field names in Zod (`aiRefId`, `title`…) | RUN-011 | ✅ | LLM writes `value-model.ts`; `prisma_zod_symmetry` checks it | **Generate `value-model.ts` from the schema** → invention impossible |
| CSS modules / barrels / top-level `types/` | RUN-012 | ✅ | LLM invents; repair-retry scaffolds after | Generate (if the project uses them) / signal absence |
| Sub-namespace dirs (`/renderers/`) | RUN-013 | ✅ | LLM invents; repair-retry collapses after | Generate the directory skeleton from the plan's file manifest |

**Why generation (vs injection/repair).** Injection still relies on the LLM *obeying* the
truth (Approach A's own OQ-4 admits no 100% adherence). Repair fixes it *after* the LLM has
already burned the generation cost and possibly cascaded (RUN-013's un-masked TS2345).
Generation removes the LLM from the mechanical artifact entirely: **zero invention, zero
adherence risk, zero repair needed.**

---

## 2. Goal

Provide a deterministic (no-LLM) generator that emits the project's **mechanical** frontend
artifacts — first and foremost the **Prisma→Zod/TS schema types** — following the **project's
own conventions**, with output that passes the existing structural validators **by
construction**, so those artifacts are never LLM-generated and never invented; reserving the
LLM for semantic work. Phased: the renderer first, the broader skeleton + pipeline ownership
later.

---

## 3. Functional Requirements

### FR-1 — Prisma→Zod/TS schema renderer (Phase A, the core)
A function/CLI that reads `prisma/schema.prisma` (via `parse_prisma_schema`) and emits the
TypeScript Zod-schema file (the `value-model.ts` equivalent): one `export const <Model>Schema =
z.object({…})` per model, with field names, types, and optionality taken **verbatim** from the
schema. No field is invented, omitted, or renamed.
*Acceptance:* rendering the strtd8 schema produces a `value-model.ts` whose every `z.object`
field set **equals** the corresponding Prisma model's `field_names` (scalars), with `?`→
`.nullable()`; the run-011 invented names (`aiRefId`, `label`, `outcomeId`, `title`,
`supportingEvidence`) are **structurally impossible** to emit.

### FR-2 — Deterministic convention layer
Apply a small, **rule-based** (no-LLM) mapping beyond raw Prisma: scalar→Zod type
(`String→z.string()`, `DateTime→z.string().datetime()`, `Json→z.unknown()`, etc.); optionality
(`?`→`.nullable()`); format hints by field-name convention (`email`→`.email()`, `*Url`/`*Uri`→
`.url()`); relation fields excluded; `@id`/provenance fields rendered per the documented mapping.
The rule set is **declared once** (seeded from the project's documented mapping) and applied
deterministically.
*Acceptance:* a field named `email` renders `.email()`; a `*Url` field renders `.url()`; a
relation field is **absent**; the same schema renders **byte-identical** output across runs.

### FR-3 — Output passes the symmetry validator by construction
The rendered file MUST pass `validators/prisma_zod_symmetry.check_prisma_zod_symmetry` with
**zero** violations — turning that validator from a *post-hoc LLM-drift detector* into a
**generator regression guard** (the generator cannot, by construction, produce drift).
*Acceptance:* `check_prisma_zod_symmetry(rendered_output, schema)` returns `[]` for every model;
a deliberately broken renderer (e.g. dropping a field) is **caught** by this gate in CI.

### FR-4 — Ownership marker + regenerability
Every generated file carries a header marking it **generated** (`// GENERATED from
prisma/schema.prisma — do not edit by hand; regenerate via <command>`) and is **idempotent**
(same schema → byte-identical) and **regenerable** (schema change → re-emit). A generated file
is **owned** by the generator, not the LLM (FR-7).
*Acceptance:* two renders of the same schema are byte-identical; the header is present; a schema
field addition re-emits with the new field.

### FR-5 — Project-convention detection
Derive conventions from the **project**, not LLM priors: the `@/` alias + roots from
`tsconfig.json` `paths`; whether the project uses barrels / CSS-modules / a `types/` dir (from
existing files). Generation **follows** these — and the **absence** of a convention (strtd8 uses
no barrels, no CSS modules) is an explicit output that *prevents* the corresponding invention
class, not just fills it.
*Acceptance:* against strtd8, detection reports `alias=@/→./`, `barrels=false`,
`css_modules=false`; the generator emits **no** barrel/CSS files and records "project does not
use barrels/CSS modules" (the RUN-012 anti-invention signal).

### FR-6 — Skeleton generators for the other mechanical artifacts (Phase B, gated)
For the remaining fully-mechanical artifacts, reuse existing primitives **gated on FR-5
detection**: barrels (`scaffold_barrel`) **only if** the project uses them; CSS-module stubs
(`scaffold_cofile`) only if it does; `package.json`/`tsconfig` (`generate_dependency_file`/
`generate_tsconfig`); the directory skeleton from the plan's file manifest (prevents RUN-013
sub-namespace invention).
*Acceptance:* on a project that uses barrels, the barrel is generated; on strtd8 (no barrels),
none is — and neither is invented.

### FR-7 — Ownership boundary: owned vs seeded
Two classes, declared per artifact: **owned** = fully deterministic, the LLM **never** writes or
edits it (schema types, barrels, css stubs, config); **seeded** = a deterministic scaffold the
LLM **completes** (route/page shells with correct imports + handler signature, body left to the
LLM). Only *owned* files are generated outright; *seeded* files are starting points. The
mechanical-vs-semantic boundary is explicit, not implicit.
*Acceptance:* the generator's manifest tags each output `owned` or `seeded`; an `owned` file has
no LLM-editable region; a `seeded` route shell has the imports + `export async function POST(req):
Promise<Response>` with a clearly-marked body stub.

### FR-8 — Standalone CLI + a pipeline ownership seam (Phase C)
Phase A/B ship as a standalone command (`startd8 generate frontend --schema <path> --out <dir>
[--project <root>]`). A later **pipeline seam** lets the prime-contractor treat *owned* files as
**provided inputs** — excluded from the LLM feature set, present on disk before generation, and
referenced (not regenerated) by dependent features.
*Acceptance (Phase A/B):* the CLI renders the schema types + applicable skeleton to `--out`.
*Acceptance (Phase C, deferred):* a prime-contractor run with the schema-types file *provided*
does **not** list it as an LLM feature and dependent features import it by its canonical path.

### FR-9 — strtd8 acceptance gate (headline)
Regenerate `lib/value-model.ts` from the **real** strtd8 schema (12 models): the output passes
`prisma_zod_symmetry` (FR-3) **and** is structurally equivalent to the hand-authored file (same
models, same scalar fields, same optionality, relations excluded). Confirm the RUN-011
field-invention set cannot be produced.
*Acceptance:* per-model field-set equality vs the committed `value-model.ts`; 0 symmetry
violations; a diff report of any *intentional* convention differences (format hints).

### FR-10 — Deterministic, no-LLM, idempotent
The entire capability makes **zero** LLM/network calls; same inputs → same bytes; safe to run
repeatedly.
*Acceptance:* runs with no API keys; two runs produce identical output.

---

## 4. Non-Functional Requirements

- **NFR-1 No-LLM + deterministic.** Pure Python; reproducible bytes.
- **NFR-2 Reuse-not-rebuild.** Build on `prisma_parser`, `scaffold_*`, `generate_tsconfig/dependency_file`, `prisma_zod_symmetry` — the renderer is the one net-new piece.
- **NFR-3 Project-truthful.** Follow the project's detected conventions (FR-5), never LLM priors; absence of a convention is a first-class signal.
- **NFR-4 Owned files are inert to the LLM.** Generated (owned) files are marked and (Phase C) excluded from the LLM surface so they can't drift.
- **NFR-5 Symmetry-by-construction.** The renderer is validated by the existing symmetry checker as a CI gate (FR-3), not trusted blindly.

---

## 5. Non-Requirements (v1)

- **NOT** generating business logic — `lib/ai/*` enrichment, route algorithms, page UX/interaction stay **LLM-authored** (semantic).
- **NOT** the full app — only the mechanical skeleton (owned) + shells (seeded).
- **NOT** replacing Approach A or repair-retry — generation is the *prevention-by-construction* layer; injection grounds the semantic bodies, repair-retry is the after-the-fact net for whatever still slips.
- **NOT** a Prisma-client replacement — this emits **app-level Zod/TS** (the `value-model.ts` mirror), not the Prisma client (`prisma generate` already does that).
- **NOT** (v1) the pipeline ownership integration (FR-8 Phase C) — deferred; the renderer ships standalone first.

---

## 6. Open Questions

- **OQ-1 — Renderer scope for v1.** Just the Prisma→Zod schemas, or also derived TS interfaces /
  enums / the `Mode` union? *(Lean: Zod schemas first — that's the RUN-011 surface; TS interfaces are a thin follow-on since Zod gives `z.infer`.)*
- **OQ-2 — Convention rule source.** Hardcode the documented mapping (email/url/provenance) vs a
  per-project config vs infer from the existing `value-model.ts`? *(Lean: a declared default rule
  set + optional per-project override; do **not** infer from LLM-authored files.)*
- **OQ-3 — Phase C pipeline mechanics.** How does the prime-contractor learn a file is *owned*
  (a manifest tag? a `provided_files` input? a plan annotation?) and exclude it from features +
  order dependents after it? *(Plan to resolve; affects forward-manifest / plan-ingestion.)*
- **OQ-4 — Seeded-shell ownership conflict.** If the LLM completes a *seeded* route shell, who
  owns the imports the generator wrote — is the shell regenerable without clobbering the LLM body?
  *(Lean: generator owns only the import block + signature; body is a guarded region.)*
- **OQ-5 — Schema drift / migrations.** On a schema change, regenerate owned files — but the LLM
  bodies that *consumed* the old shape may break. How is that surfaced? *(Likely: regen + a diff
  that flags consuming features for review/regen — ties back to repair-retry's worklist.)*
- **OQ-6 — Where the renderer lives.** A new `frontend_codegen/` module? Extend
  `languages/nodejs`? Reuse `contractors/project_knowledge`? *(Plan to resolve; lean: a focused
  `codegen/` package the prime-contractor + CLI both call.)*

---

## 7. Relationship to the roadmap

- **Realizes** the structural fix RUN-011/012/013 all named — as **generation**, the
  cheapest of the three levers (injection / repair / generation).
- **Repurposes** `prisma_zod_symmetry` from an LLM-drift detector into a generator regression
  guard (FR-3) — same validator, stronger guarantee.
- **Composes** with Approach A (grounds the *semantic* bodies) and repair-retry (the net for the
  residue) — generation removes the *mechanical* surface from both their workloads.
- **Sequenced:** Phase A renderer (kills RUN-011) → Phase B skeleton (RUN-012/013 mechanical) →
  Phase C pipeline ownership (the LLM never sees the owned files).

---

*v0.2 — Post-planning self-reflective update: "100% derivable" corrected to "derivable from
schema + documented conventions" (FR-2); scope phased (renderer first, pipeline ownership later);
`prisma_zod_symmetry` reframed as a generator regression guard (FR-3); two ownership models added
(owned vs seeded, FR-7); project-convention detection added (FR-5) — strtd8's *absence* of
barrels/CSS is itself the anti-invention signal. Pairs with `DETERMINISTIC_FRONTEND_GENERATION_PLAN.md`.
CRP review offered before implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

### Appendix A: Applied Suggestions
_None yet._

### Appendix B: Rejected Suggestions (with Rationale)
_None yet._

### Appendix C: Incoming Suggestions (Untriaged, append-only)
_Awaiting first review round._
```

---

## Begin

Produce your **suggestions** now and **append them to the source files** via Write/Edit (see **Your Task**, **Deliverables**, and **Scope lock** above). Source file paths are in the **Source documents** table at the top of this prompt.

Checklist before your **final** chat reply:

- [ ] Read each source file's Appendix A/B/C; did not re-propose settled (A) or rejected (B) items, nor near-duplicate untriaged (C).
- [ ] Appended a `#### Review Round R{n}` block under **Appendix C** of each source file in scope (initialized the A/B/C scaffold if it was absent).
- [ ] Round block contains: executive summary (≤10 bullets) + numbered suggestions (**R{n}-S\*** / **R{n}-F\***); optional adversarial subsection; optional Endorsements & Disagreements block.
- [ ] Did not modify existing prose, populated Appendix A/B, or prior rounds in C.
- [ ] Appended `## Requirements Coverage Matrix — R{n}` section to the end of the **plan** file (after your round block).
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (initializing an absent A/B/C scaffold is fine).
