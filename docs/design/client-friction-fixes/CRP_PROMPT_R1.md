# Convergent Review Prompt

**Generated:** 2026-07-09 17:14:38 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 10 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/client-friction-fixes/PLAN.md` | 259 lines · 1761 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/client-friction-fixes/REQUIREMENTS.md` | 240 lines · 2418 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/client-friction-fixes/CRP_FOCUS.md` | 48 lines · 459 words |

Treat the embedded documents below as **read-only ground truth** for this review. If something conflicts between plan and requirements, call it out explicitly in suggestions and in the coverage mapping.

---

## Your Task

You are a **senior architectural reviewer** with **file-edit tools** (Write/Edit/equivalent) and filesystem access to the source documents listed above. Your job is to produce **improvement suggestions** (structured, anchored, actionable) and **persist them directly into the source documents** by appending a new **Review Round** under each reviewed document's **Appendix C (Incoming)** — see **Prior Review State** below.

**First, read the existing review state** (Appendix A/B/C) in each source doc and **avoid re-proposing** what is already settled (A) or rejected (B), and **avoid near-duplicates** of untriaged items in C (dedup rules below). Every in-scope doc already contains a `## Appendix: Iterative Review Log` with an empty A/B/C scaffold (the generator created it) — **append your round to Appendix C**; do **not** create a second scaffold.

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
| Max suggestions (soft cap) | 10 |
| Review areas to consider | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |

### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

# CRP Focus — Client-Friction Fixes (deferred, open-question steps)

Weight the review on the three **least-reviewed** steps; the P0/P1 codegen fixes are already
implemented and merged (PR #175) and are **out of scope** for this review.

## Where we need input most

### 1. FR-F3 / Step 3 — `has one` full one-to-one support
`has one <X>` currently emits `X[]` (one-to-many) because the grammar
(`manifest_extraction/entities.py:409`) treats `has one` and `has many` identically, and the
Prisma emitter decides cardinality by FK ownership, not the verb. OQ-4 is resolved to **full
support**: thread a `cardinality="one"` signal end-to-end → singular relation (`X?`) + `@unique` on
the child FK (which, with the now-merged F3b, becomes a real DB constraint).
- **Press on:** self-relations, optional-vs-required one-to-one, existing schemas that already say
  `has many`, and whether adding `@unique` to a child FK can silently break existing many-row data.
  Is the flag-as-unsupported fallback (FR-F3-iii) the safer first landing?

### 2. FR-F1/F8 / Step 6 — in-table `choice of:` truncation + kickoff-check sanity (OQ-7)
The Markdown table splitter breaks `| status | choice of: a|b|c |` at the first `|`, so the enum
extracts to a single value; `kickoff check` reports "docs conform" (false-green). Fix adds a
value-level `choice-of-single-value` signal keyed to `Entity.field`.
- **Press on OQ-7:** should a multi-value `choice of:` that extracts to ONE value be a **hard**
  `kickoff check --strict` failure (exit non-zero) or a **warning**? Hard is safer for silent data
  loss but false-positives on a legitimately single-value closed vocabulary. What disambiguates a
  truncation from a genuine single-member enum?

### 3. FR-H4 / Step 7 — VIPP entity-field capture disposition honesty (OQ-5)
A `capture` of `<Entity>.<field>` (e.g. `Chore.name`) is ACCEPT[VALIDATED] at negotiate
(`vipp/evaluate.py`) but refused `value_path_not_allowed` at apply (`proposals.py:308-311`), because
VIPP's FIELD_AUTHORITY namespace (`Chore.name`) differs from the kickoff apply-floor allow-list
namespace (`conventions.yaml#/language`). Reframed (NR-4): do **not** widen the floor; make the
disposition honest.
- **Press on OQ-5:** ACCEPT-but-inert (carry a `value_path_not_allowed`/`not-mapped` qualifier) vs
  OMIT-with-reason at negotiate? Which reads more honestly in the disposition report and avoids the
  "wrote 1/2" silent-partial? Is there a third disposition the VIPP model already supports?

## Settled — do NOT relitigate
- H1 (wireframe `KeyError 'api'`) and H2 (MCP `questionary`) are **already fixed** (NR-1).
- F13, F3b, F2, H3 are **implemented + merged** (PR #175) — out of scope.
- Widening the kickoff apply-floor allow-list to entity-field paths is **rejected** (NR-4 / FR-H4c).
- P3 DX findings (F4–F11) are **deferred** (NR-2).

## Also weigh
- **OQ-6** (Step 8): should authored `observability.yaml` **override** the manifest when present, or
  **merge** (and with what precedence)? The generator already accepts the param; only wiring +
  precedence is undecided.
- Cross-cutting **FR-0**: every fix must ship a regression test that fails on `main`. Flag any
  proposed step that lacks a clear failing-first test.

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

1. **Append a `#### Review Round R{n} — <your-model-id> — <UTC date>`** block under **Appendix C (Incoming)** of each source document you reviewed (plan suggestions → plan file; requirements suggestions → requirements file). The `## Appendix: Iterative Review Log` scaffold already exists (generator-created) — append to its Appendix C. Use Write/Edit; do **not** modify existing prose, Appendix A/B, or prior rounds.
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
- Use file-edit tools to **append a `#### Review Round R{n}` block** under **Appendix C** of each reviewed doc, computing **n** = highest existing round + 1 (or 1). The `## Appendix: Iterative Review Log` scaffold is **pre-initialized by the generator** — append to it; do not recreate it.
- In dual mode, also append a `## Requirements Coverage Matrix — R{n}` section to the end of the plan file.
- If tokens remain, add an **Endorsements & Disagreements** block on untriaged prior suggestions.

**You MUST NOT:**

- Triage (no ACCEPT/REJECT disposition for your own or others' suggestions) — that is orchestrator-side and lands in Appendix A/B.
- Modify, rewrite, reorder, or delete existing prose, **populated** Appendix A/B, or **prior rounds** in Appendix C. (The A/B/C scaffold is generator-created — do **not** add a second one.)
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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/client-friction-fixes/PLAN.md`  ·  **Size:** 259 lines · 1761 words

```markdown
# Client-Logged Friction Fixes — Implementation Plan

**Version:** 1.0 (post-planning, paired with REQUIREMENTS v0.2)
**Date:** 2026-07-09
**Branch:** `fix/client-friction-triage-p0p2`

Sequenced by (1) severity and (2) dependency. Each step names the edit locus, the change, and the
regression test that must fail on `main` and pass after (FR-0). All loci re-verified this session.

---

## Sequencing rationale

1. **P0 codegen first** (F13, F3b) — highest severity (silent data corruption), smallest blast radius,
   two files, no cross-module dependencies.
2. **F3b before F3** — F3 (`has one`) needs `@unique` to actually reach `tables.py` to be
   end-to-end verifiable; F3b provides that emission.
3. **P1 crashes** (F2, H3) — localized `view_codegen` guards.
4. **F1/F8** — extraction sanity check (touches `manifest_extraction` + `cli_kickoff`).
5. **P2 honesty** (H4, H5) — VIPP disposition + observability wiring; independent, can parallelize.

---

## Step 1 — FR-F13: `yes/no` boolean defaults

**1a. Renderer (defensive).** `src/startd8/backend_codegen/sqlmodel_renderer.py`,
`_default_field_arg` (line 65). Before the numeric/bareword fallthrough (line 93-97), add:
```python
if field.type == "Boolean" and val in ("yes", "no"):
    return f"default={'True' if val == 'yes' else 'False'}"
```
Place it alongside the existing `("true", "false")` branch (line 93). Gate on `field.type ==
"Boolean"` so a `String @default(yes)` (a legit enum member) is untouched.

**1b. Emitter (canonical).** `src/startd8/manifest_extraction/prisma_emitter.py` — where a
`yes/no … default:` boolean field is emitted. Emit `@default(false)` / `@default(true)` instead of
`@default(no|yes)`. (Locate the boolean-default emission; confirm the prose→default mapping.)

**Regression test:** `tests/unit/backend_codegen/test_sqlmodel_renderer.py` — a schema with
`active Boolean @default(no)` must render `Field(default=False)` (not `default="no"`). Add a matching
emitter test that `yes/no default: no` prose emits `@default(false)`. Assert on `main` the render is
`default="no"`.

---

## Step 2 — FR-F3b: emit `@unique` / `@@unique`

**2a. Field-level `@unique`.** `sqlmodel_renderer.py`, `_render_table_field` (line 253). The function
already composes `args` from `is_pk`/`fk`/`default_arg` (line 279-285). Add:
```python
if field.is_unique and not is_pk:   # PK is already unique
    args.append("unique=True")
```
`PrismaField.is_unique` already exists (`prisma_parser.py:62`). No signature change needed.

**2b. Model-level `@@unique`.** Composite uniqueness lives in `PrismaModel.block_attributes` /
`compound_unique_keys` (`prisma_parser.py:100-110`). In the **table-class** renderer (the function
that emits `class X(SQLModel, table=True)` and already handles compound `@@id` via
`_compound_pk_cols`), add a `__table_args__` line when `compound_unique_keys` (excluding any that
equal the compound PK) is non-empty:
```python
__table_args__ = (UniqueConstraint("assignmentId", name="uq_review_assignmentId"),)
```
Requires importing `UniqueConstraint` from `sqlalchemy` in the generated file's imports (thread a
`needs.add("uniqueconstraint")` and add the import line to the import emitter, mirroring the existing
`Column`/`JSON` import handling). Skip any compound-unique tuple identical to the model's `@@id`.

**Regression test:** `tests/unit/backend_codegen/test_sqlmodel_renderer.py` — (i) `email String
@unique` → `Field(..., unique=True)`; (ii) `@@unique([assignmentId])` → `__table_args__` with
`UniqueConstraint`; (iii) a `@@unique` equal to `@@id` emits **no** duplicate constraint;
(iv) idempotency `--check` unchanged for schemas with no unique (FR-0b).
**Lesson note (Testing #9):** these tests instantiate SQLModel tables → SQLModel's process-global
`MetaData` survives `sys.modules` purges. Drop owned tables at setup **and** teardown (scoped
`md.remove`, not `md.clear`) to avoid a cross-test collision / false-green.

---

## Step 3 — FR-F3: `has one` one-to-one (gated by OQ-4)

**Decision needed (OQ-4).** Two landing options:
- **Minimal (recommended if time-boxed):** FR-F3-iii only — in the grammar/extraction, when verb ==
  `has one`, emit a `kickoff check` warning `has-one-unsupported` (no silent has-many). Small, honest.
- **Full:** thread verb cardinality end-to-end.

**Full-support edits:**
- `src/startd8/manifest_extraction/entities.py:409` — split `has one` from `has many`; carry a
  `cardinality="one"` signal on the relation record (line 421 currently builds the same FK value for
  both).
- `src/startd8/manifest_extraction/prisma_emitter.py` — for a `cardinality="one"` relation, emit the
  parent side as singular (`X?`) and add `@unique` to the child FK scalar. With Step 2 (FR-F3b) this
  becomes a real DB constraint.

**Regression test:** extraction golden — `an Assignment has one Review` produces `review Review?`
(singular) with `@unique` on `Review.assignmentId`; end-to-end, the generated `tables.py` has
`unique=True` on the FK (depends on Step 2). On `main`, assert it emits `reviews Review[]`.

---

## Step 4 — FR-F2: `board` empty-order → clear error

**4a. Parse-time guard (guaranteed).** `src/startd8/view_codegen/manifest.py` — in `parse_views`
(order defaulted at line 447) or `ViewSpec` post-init, when `kind == "board"` and `order` is empty:
```python
raise ValueError(f"board {module!r}: group_by {group_by!r} requires an Order: (declared enum values)")
```
**4b. Test-emitter guard (defense-in-depth).** `src/startd8/view_codegen/renderers.py:1550` — the
crash site. With 4a no board spec reaches it empty, but add an explicit guard so the emitter never
does an unguarded `v.order[0]`.

**4c. (OQ-5/FR-F2b, optional).** If `parse_views` is given `known_enums`, default `order` to the
group-by enum's values. Only if it threads cleanly from the caller (`cli`/generate views), which
already has the parsed schema/enums.

**Regression test:** `tests/unit/view_codegen/test_*` — a `board` view, enum `group_by`, no `order`
→ `ValueError` naming the view (not `IndexError`). On `main`, assert `IndexError` is raised (the bug).

---

## Step 5 — FR-H3: `workspace` non-polymorphic → clear error

`src/startd8/view_codegen/renderers.py:150-152` — replace:
```python
p = v.polymorphic
assert p is not None
```
with:
```python
p = v.polymorphic
if p is None:
    raise ValueError(
        f"workspace {v.module!r}: requires a polymorphic relation "
        f"(of/type_field/id_field/type_map); root {v.root!r} has none"
    )
```
(Consider validating at `parse_views` too, mirroring Step 4a, so it fails at spec-load not render.)

**Regression test:** a `workspace` view with a non-polymorphic root → `ValueError` naming the view.
On `main`, assert bare `AssertionError`.

---

## Step 6 — FR-F1/F8: choice-of value-level sanity + docs

**6a. Extraction signal.** `src/startd8/manifest_extraction/entities.py:237` (after `enum_values`
computed, before the field record is appended, ~237-253): when the field is `choice of:` and
`len(enum_values) == 1`, emit an extraction record `choice-of-single-value` keyed to
`Entity.field` (suspicious truncation). Decide hard-vs-warn per **OQ-7**.

**6b. kickoff check surfacing.** `src/startd8/cli_kickoff.py` — ensure `_is_conformance_failure`
(line 51-56) treats the new record appropriately (hard failure under `--strict` if OQ-7 = hard;
otherwise a printed warning that keeps exit 0 but is visible).

**6c. Docs.** Update the FORMAT worked example to show `choice of:` **inside a table** with
`\|`-escaped pipes (FR-F1b). Optionally (FR-F1c) detect an unescaped in-table `choice of:` `|` in
`grammar.md_tables` (`grammar.py:101-126`) and warn.

**Regression test:** a REQUIREMENTS-format doc with `| status | choice of: a\|b\|c |` inside a table,
unescaped, extracting to a single value → `kickoff check` reports `choice-of-single-value` (not "docs
conform"). On `main`, assert `kickoff check` reports conform (the false-green bug).

---

## Step 7 — FR-H4: VIPP entity-field capture disposition honesty

**Edit:** `src/startd8/vipp/evaluate.py` (~199-205, the ACCEPT return). A `capture` proposal whose
value-path is a `<Entity>.<field>` symbol that VIPP validated via FIELD_AUTHORITY, but which has **no
writable target** in the kickoff manifest, must be adjudicated **ACCEPT-but-inert** — carry a
qualifier/reason (`value_path_not_allowed` / `not-mapped-to-kickoff-inputs`) so the disposition does
not imply an applicable write. (Per FR-H4c / NR-4, do **not** touch `proposals.py`/`manifest.py` to
widen the floor.)

Decide the exact disposition per **OQ-5** (ACCEPT-but-inert vs OMIT-with-reason).

**Regression test:** `tests/unit/vipp/test_evaluate.py` — a `capture` of `Chore.name` (a real field)
adjudicates to the inert/qualified disposition, and a full negotiate→apply run reports it as **inert,
not `wrote 1/2`**. On `main`, assert negotiate returns a plain ACCEPT[VALIDATED] that apply then
refuses (the dishonest split).

---

## Step 8 — FR-H5: observability.yaml wiring

**8a. SDK-side (in-repo).** `scripts/generate_observability_artifacts.py`:
- Add `--observability-yaml` argparse flag (optional, mirror `--manifest` at line 64-68).
- Thread `observability_yaml_path=Path(args.observability_yaml) if args.observability_yaml else None`
  into both `generate_observability_artifacts(...)` call sites (~142, ~173). The function already
  accepts the parameter (line 426).

**8b. Cross-repo (tracked separately, FR-H5b).** `~/Documents/dev/cap-dev-pipe/pipeline/stages/
observability.py:32-86` — add `observability_yaml_path` to `run_observability()` and pass it to
`generate(...)`. **This is the canonical cap-dev-pipe repo (symlinked)** — land as its own change
with its own branch/PR, not folded into this SDK PR.

**8c. Docs (FR-H5c).** Update `NEXT_STEPS` / `O11Y_CORE_BUILD_RUNBOOK` to state the real contract and
the precedence rule chosen in **OQ-6** (override vs merge).

**Regression test:** `scripts/` or unit test — invoking the generator with `--observability-yaml`
threads the path to `generate_observability_artifacts` (assert the param is received/consumed). Doc
change verified by inspection.

---

## Verification gate (before merge)

- [ ] Each step's regression test **fails on `main`**, **passes on branch** (FR-0).
- [ ] `pytest tests/unit/backend_codegen tests/unit/view_codegen tests/unit/vipp` green.
- [ ] `generate backend --check` / `generate views --check` idempotency unchanged on a schema that
      does **not** exercise any fix (FR-0b) — no drift.
- [ ] Run the two P0 fixes against the **portal-rebuild** and **household-o11y** schemas that
      originally logged them; confirm the friction no longer reproduces.
- [ ] `ruff check src/` + `black src/` clean on edited files.
- [ ] Branch-first → PR (never commit to `main`); Stage-7 (FR-H5b) filed as a separate cap-dev-pipe PR.

---

## Effort estimate

| Step | Files | Size | Risk |
|------|-------|------|------|
| 1 (F13) | 2 | S | low |
| 2 (F3b) | 1 (+import emitter) | M | low-med (import threading) |
| 3 (F3) | 2 | M (full) / S (flag-only) | med — **OQ-4** |
| 4 (F2) | 1-2 | S | low |
| 5 (H3) | 1 | S | low |
| 6 (F1/F8) | 2-3 | M | med — **OQ-7** false-positive tuning |
| 7 (H4) | 1 | S-M | med — **OQ-5** disposition semantics |
| 8 (H5) | 1 in-repo (+1 cross-repo) | S | low (in-repo) |

Recommended first landing: **Steps 1, 2, 4, 5** (the four P0/P1 codegen fixes — smallest, highest
severity, no open questions). Steps 3/6/7 carry open questions to resolve (or CRP) first; Step 8 is
independent and low-risk.

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/client-friction-fixes/REQUIREMENTS.md`  ·  **Size:** 240 lines · 2418 words

```markdown
# Client-Logged Friction Fixes — Requirements

**Version:** 0.3 (Post lessons-learned hardening)
**Date:** 2026-07-09
**Status:** Draft (pre-CRP)
**Branch:** `fix/client-friction-triage-p0p2`

**Provenance:** Friction logged by two live downstream projects, re-verified against current
source this session:
- `~/Documents/dev/household/household-o11y/concierge-friction.jsonl` (entries H1–H5)
- `docs/PORTAL_REBUILD_FEEDBACK_FROM_CONSUMER_2026-07-08.md` (findings F1–F13)

The navig8 friction log (`docs/design/kickoff/CONCIERGE_FRICTION_LOG_NAVIG8.md`, F-1..10) is
onboarding *process* friction, not SDK bugs — **out of scope** here.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (report-based assumptions) and v0.2 (after reading current source).
> The planning pass re-verified every code claim and corrected three material assumptions.

| v0.1 Assumption (from the reports) | Planning Discovery | Impact |
|---|---|---|
| H4: fix by "widening the apply floor allow-list for validated entity-field captures" | The kickoff apply floor's allow-list is **config-YAML value-paths** (`conventions.yaml#/language`, `manifest.py:133-135`), a *different namespace* from VIPP negotiate's `<Entity>.<field>` FIELD_AUTHORITY check (`evaluate.py:75-91`). There is **no `write_target`** for project entity fields — widening is infeasible/wrong. | **FR-H4 reframed**: make the negotiate disposition honest (ACCEPT-but-inert / non-actionable), not widen a floor. |
| F2: board crash is in the view *data* renderer | The board **data** renderer (`renderers.py:81`) is already **safe** on empty `order`. The `IndexError` is only in the board **test emitter** (`renderers.py:1550`, `v.order[0]`). | **FR-F2 split**: (a) guard the test emitter; (b) validate at parse time. Auto-derive from enum needs a loader signature change (enums not threaded into `parse_views`) → optional, not the core fix. |
| H5: `observability.yaml` needs a new generator parameter | `generate_observability_artifacts()` **already accepts** `observability_yaml_path` (`scripts/generate_observability_artifacts.py:426`); it is simply **never wired** by the CLI or Stage 7. Stage 7 lives in the **canonical `cap-dev-pipe` repo** (symlinked), so that half is cross-repo. | **FR-H5 narrowed**: SDK-side = add the script flag + thread the two `generate(...)` calls (in-repo, low-risk). Stage-7 wiring is a **separate cross-repo task** (or documented as manifest-SSOT). |
| F13: fix the SQLModel renderer | Root cause is upstream too: the Prisma **emitter** turns `yes/no default: no` into `@default(no)` (a bareword). A hand-authored schema hits the same renderer bug. | **FR-F13 = belt-and-suspenders**: fix the emitter (source) *and* make the renderer defensive (gate on `Boolean`). |
| F3 (`has one`) and F3b (`@unique` dropped) are separate | They are **two halves of one-to-one**: F3 must get `@unique` onto the child FK *in the schema*; F3b must carry `@unique` *from schema into `tables.py`*. Neither alone enforces uniqueness. | Sequence F3b first (schema→table), then F3 (prose→schema); F3's regression test depends on F3b's emission. |
| F2 auto-derives board order from the group-by enum | The loader `parse_views(text, *, known_entities, known_fields)` (`manifest.py:187`) has **no enum values** in scope. Auto-derivation requires threading `known_enums`. | Auto-derive demoted to an **optional enhancement (FR-F2b)**; the guaranteed fix is flag-don't-crash. |

**Resolved open questions:**
- **OQ-1 → Fix at both layers for F13.** Emitter emits canonical `@default(false|true)`; renderer stays defensive for hand-authored schemas.
- **OQ-2 → H4 is a disposition-honesty fix, not an allow-list widening.** (See discovery above.)
- **OQ-3 → H5 SDK-side is in-scope and small; cap-dev-pipe Stage 7 is a tracked cross-repo follow-up**, not blocked on here.

---

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/` (Design_Docs + SDK_developer, lesson 9 Testing Patterns) before
> CRP. Applicable lessons — each changed the spec/plan:

- **[Testing #9 — regression attribution via base-commit worktree repro / "fail on main, pass on
  branch"]** → hardened **FR-0**: each regression test must be demonstrated red on `main` *before*
  the fix, not just green after. Added to the plan's per-step tests and the verification gate.
- **[Testing #9 — SQLModel process-global `MetaData` survives `sys.modules` purge (drop owned tables
  at start + teardown; scoped `md.remove`, not `md.clear`)]** → **plan Step 2 (FR-F3b) test note**:
  the `@unique`/`UniqueConstraint` tests instantiate SQLModel tables, so they must drop owned tables
  at setup+teardown to avoid the process-global metadata collision. Prevents a flaky/false-green.
- **[Testing #9 — golden-snapshot capture-lock-refactor-verify (JSON tuple→list false-fail)]** →
  **FR-0b** idempotency assertions compare rendered *text*, not re-serialized structures, to avoid
  tuple→list snapshot false-fails.
- **[Phantom-reference audit]** → every locus named in REQUIREMENTS/PLAN was re-verified to exist
  this session with an exact `file:line` + quote (H1/H2 confirmed *already fixed*, so excluded per
  NR-1). No phantom symbols remain.

**Least-reviewed target for CRP (steering memory):** the **VIPP disposition reframe (FR-H4)** and the
**`has one` grammar/emitter change (FR-F3)** — both carry open questions (OQ-4, OQ-5) and the least
prior design review. **Settled / do-not-relitigate:** H1/H2 are already fixed (NR-1); widening the
apply-floor allow-list is rejected (NR-4/FR-H4c); the P3 DX findings are deferred (NR-2).

---

## 1. Problem Statement

Five deterministic **$0-path** codegen/DX bugs and two contract-honesty gaps, all logged by real
consumers, survive the SDK's existing gates. The unifying failure mode is **silent-wrong**: the
generator emits code that compiles and runs but is *semantically incorrect* (a truthy string where a
boolean was meant; a missing DB constraint; a one-to-many where one-to-one was specified), or crashes
with a **bare, unkeyed exception** instead of a clear, actionable error. Per the SOTTO/HAYAI
principles, a $0 deterministic path must not silently corrupt data or crash without naming the
offending artifact.

| ID | Severity | Current State | Gap | Verified locus |
|----|----------|---------------|-----|----------------|
| **F13** | P0 (data/security) | `yes/no default: no` → `Field(default="no")` (truthy string) | boolean default is `True` when author meant `False` (operator-by-default) | `sqlmodel_renderer.py:91-97` + emitter |
| **F3b** | P0 (data integrity) | `@unique`/`@@unique` parsed but never emitted | tables have **no** unique constraints; uniqueness is advisory-only | `prisma_parser.py:62` (parsed) vs `sqlmodel_renderer.py:277-303` (not emitted) |
| **F1/F8** | P0 (silent data loss) | in-table `choice of: a\|b\|c` truncates to first value; `kickoff check` says "docs conform" | enum silently loses values; the first gate is falsely green | `grammar.py:111`, `entities.py:237`, `cli_kickoff.py:129` |
| **F2** | P1 (crash) | `board` view, enum `group_by`, no `Order:` → bare `IndexError` | hard crash, no view name, blocks cascade | `renderers.py:1550` (test emitter) + `manifest.py:447` (loader) |
| **H3** | P1 (crash) | non-polymorphic `workspace` root → bare `AssertionError` | hard crash, no view name | `renderers.py:150-152` |
| **F3** | P2 (modeling) | `has one` treated identically to `has many` → `Review[]` | one-to-one intent lost at schema level | `entities.py:409` (verb), `prisma_emitter.py` (cardinality) |
| **H4** | P2 (honesty) | entity-field `capture` ACCEPT[VALIDATED] at negotiate, refused `value_path_not_allowed` at apply | disposition over-promises a write that cannot happen | `evaluate.py:75-91`/`199-205` vs `proposals.py:308-311` |
| **H5** | P2 (honesty) | authored `observability.yaml` not read by shipped path | authored thresholds/SLOs silently omitted | `scripts/generate_observability_artifacts.py:426` (accepted, unwired) |

---

## 2. Requirements

### Cross-cutting

- **FR-0 (regression-first).** Every fix ships with a **regression test that fails on `main` and
  passes with the fix** — a golden that reproduces the exact consumer friction. The tests are as
  load-bearing as the fixes (these bugs slipped *because* no test covered the case).
- **FR-0a (flag-don't-crash).** Every "hard crash" fix (F2, H3) must raise a clear, typed error that
  **names the offending view/field** (RUN-029 style), never a bare `AssertionError`/`IndexError`.
- **FR-0b (idempotency preserved).** All codegen fixes must keep `generate … --check` parity /
  byte-identical idempotency on unaffected inputs (no drift on schemas that don't exercise the fix).

### P0 — silent-wrong

- **FR-F13.** A `yes`/`no` Prisma `@default` on a **`Boolean`** field must produce a real Python
  boolean.
  - **FR-F13a (renderer, defensive).** `_default_field_arg` maps `@default(no)`→`default=False` and
    `@default(yes)`→`default=True` **only when the field type is `Boolean`** (a bareword default on a
    non-boolean field remains a string enum member). This protects hand-authored schemas.
  - **FR-F13b (emitter, canonical).** The manifest→Prisma emitter emits `@default(false)` /
    `@default(true)` (not `@default(no|yes)`) for `yes/no … default:` boolean fields, so the schema
    itself is canonical.
- **FR-F3b.** The backend generator must emit unique constraints the parser already recognizes.
  - **FR-F3b-i.** A field-level `@unique` (`PrismaField.is_unique`) emits `unique=True` in that
    column's `Field(...)`.
  - **FR-F3b-ii.** A model-level `@@unique([a, b])` emits a `__table_args__ = (UniqueConstraint("a",
    "b"),)` on the table class (composite uniqueness). Single-column `@@unique([a])` is acceptable as
    either form.
  - **FR-F3b-iii.** Emission must not duplicate a constraint already implied by `@id`/`@@id` (PK is
    inherently unique).
- **FR-F1/F8.** Extraction must not silently truncate an in-table `choice of:` enum, and
  `kickoff check` must not report "docs conform" when it happened.
  - **FR-F1a (value-level sanity).** When a field's declared type is `choice of:` and extraction
    yields **exactly one** enum value, emit an extraction record/warning
    (`choice-of-single-value`) keyed to the entity.field — surfaced by `kickoff check`.
  - **FR-F1b (author guidance).** The FORMAT worked example shows `choice of:` **inside a table**
    with `\|`-escaped pipes (today the sample is shown outside a table, so it doesn't warn authors).
  - **FR-F1c (optional detection).** Where feasible, detect a raw table cell containing `choice of:`
    with unescaped `|` and warn/auto-unescape at parse time.

### P1 — crash → clear error

- **FR-F2.** A `board` view whose `order` is empty must not crash with `IndexError`.
  - **FR-F2a (guaranteed).** Validate at parse/spec time (`parse_views` / `ViewSpec`
    construction) that a `board` view has a non-empty `order`; if absent, raise
    `ValueError("board '<name>': group_by '<field>' requires an Order:")`. Also guard the test
    emitter (`renderers.py:1550`) so no `board` spec can reach it with empty `order`.
  - **FR-F2b (optional enhancement).** If `known_enums` is threaded into `parse_views`, derive
    `order` from the group-by enum's declared values automatically (removing the need for an explicit
    `Order:`). Deferred unless cheap.
- **FR-H3.** `_render_workspace` on a non-polymorphic root must raise
  `ValueError("workspace '<name>': requires a polymorphic relation (of/type_field/id_field/type_map); root '<root>' has none")`
  instead of `assert p is not None`. (Also decide DX per NR: `workspace` is polymorphic-only today —
  documented, not renamed, in this pass.)

### P2 — contract honesty / modeling

- **FR-F3.** `has one <X>` must model one-to-one, not one-to-many.
  - **FR-F3-i.** The relationship grammar (`entities.py:409`) must carry the verb's cardinality
    (`has one` = singular) distinctly from `has many`.
  - **FR-F3-ii.** The Prisma emitter emits a singular relation (`X?`) **and** `@unique` on the child
    FK for `has one` (which, with FR-F3b, becomes a real DB constraint).
  - **FR-F3-iii.** If full support is not landed this pass, `kickoff check` must **flag `has one` as
    unsupported** rather than silently emit has-many (no silent-wrong).
- **FR-H4.** A VIPP `capture` of a `<Entity>.<field>` value-path must have a **consistent** story
  between negotiate and apply.
  - **FR-H4a.** At **negotiate** (`evaluate.py`), a `capture` whose value-path has **no writable
    target** in the kickoff manifest must be adjudicated **ACCEPT-but-inert** (or carry an explicit
    `value_path_not_allowed`/`not-mapped` qualifier), so the disposition report does not imply a
    write the floor will refuse.
  - **FR-H4b.** The apply summary must not read as a silent partial (`wrote 1/2`) for a proposal that
    was *never* actionable; inert proposals are reported as inert, not as failed writes.
  - **FR-H4c (non-goal clarifier).** Widening the apply-floor allow-list to accept `<Entity>.<field>`
    paths is **explicitly rejected** (different namespace, no write target) — see NR-4.
- **FR-H5.** Authored `observability.yaml` must either be a **first-class input** or **documented as
  advisory-only** — never silently dropped.
  - **FR-H5a (SDK-side, in-repo).** `scripts/generate_observability_artifacts.py` gains an optional
    `--observability-yaml` flag, threaded into both `generate_observability_artifacts(...)` call
    sites (the function already accepts `observability_yaml_path`).
  - **FR-H5b (cross-repo, tracked).** cap-dev-pipe Stage 7
    (`~/Documents/dev/cap-dev-pipe/pipeline/stages/observability.py`) threads the path through
    `run_observability()` → `generate(...)`. Tracked as a **separate cap-dev-pipe change**.
  - **FR-H5c (docs).** `NEXT_STEPS` / `O11Y_CORE_BUILD_RUNBOOK` state the real contract (manifest vs
    observability.yaml) so authored intent cannot be dropped without warning.

---

## 3. Non-Requirements

- **NR-1.** No fix to the two **already-resolved** items: H1 (wireframe `KeyError 'api'`, fixed at
  `wireframe/plan.py:1138`) and H2 (MCP `questionary` ModuleNotFoundError, fixed via lazy import at
  `concierge_view.py:525,531`). Confirmed fixed this session.
- **NR-2.** Not addressing the **P3 DX** portal findings here (F4 shared named enums, F5
  relationship/FK name hints, F6 `--with-manifests` app.yaml placement, F7 `--pages` stubbing, F9
  `--gate` compile-only docs, F10 workbook UID default, F11 deployed-mode note). Logged for a later
  DX pass.
- **NR-3.** Not renaming the `workspace` view archetype (H3 DX half) — only making it flag-don't-crash
  and documenting that it is polymorphic-only.
- **NR-4.** Not widening the kickoff apply-floor allow-list to entity-field value-paths (FR-H4c).
- **NR-5.** Not building auto-derivation of board order from enums (FR-F2b) unless it falls out cheaply
  from threading `known_enums`.
- **NR-6.** Not authoring real observability thresholds/content (bucket 4) — H5 is a wiring/honesty
  fix only.

---

## 4. Open Questions

- **OQ-4 → RESOLVED (full support).** Land full `has one` one-to-one support: thread verb cardinality
  end-to-end (singular relation + `@unique` on child FK). Will pass through CRP before implementing
  (batched with H4, F1/F8). FR-F3-iii (flag-only) is the fallback if CRP surfaces a blocker.
- **OQ-5.** For FR-H4, is **ACCEPT-but-inert** the right disposition, or should such captures be
  `OMIT` with a reason at negotiate? (Affects how the VIPP disposition report reads.)
- **OQ-6.** For FR-H5, do we treat `observability.yaml` as authoritative-when-present (override
  manifest) or additive (merge)? Merge semantics need a precedence rule.
- **OQ-7.** F1/F8: is the value-level `choice-of-single-value` signal a **hard** conformance failure
  (`kickoff check --strict` exits non-zero) or a **warning**? Hard = safer (matches "silent data
  loss"), but may false-positive on a legitimately single-value closed vocabulary.

---

*v0.3 — Post lessons-learned hardening. Applied 4 SDK lessons (regression base-repro, SQLModel
MetaData teardown, golden-snapshot text-compare, phantom-reference audit). v0.2 reframed 3
requirements (H4, F2, H5), promoted 2 to belt-and-suspenders (F13, F3+F3b), demoted 1 to optional
(F2b), raised 4 open questions. Ready for CRP review.*

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
```

---

## Begin

Produce your **suggestions** now and **append them to the source files** via Write/Edit (see **Your Task**, **Deliverables**, and **Scope lock** above). Source file paths are in the **Source documents** table at the top of this prompt.

Checklist before your **final** chat reply:

- [ ] Read each source file's Appendix A/B/C; did not re-propose settled (A) or rejected (B) items, nor near-duplicate untriaged (C).
- [ ] Appended a `#### Review Round R{n}` block under **Appendix C** of each source file in scope (the A/B/C scaffold is generator-created — appended to it, did not recreate it).
- [ ] Round block contains: executive summary (≤10 bullets) + numbered suggestions (**R{n}-S\*** / **R{n}-F\***); optional adversarial subsection; optional Endorsements & Disagreements block.
- [ ] Did not modify existing prose, populated Appendix A/B, or prior rounds in C.
- [ ] Appended `## Requirements Coverage Matrix — R{n}` section to the end of the **plan** file (after your round block).
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (the A/B/C scaffold is generator-created — do not add another).
