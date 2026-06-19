# Convergent Review Prompt

**Generated:** 2026-06-12 03:27:40 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/view-prose/VIEW_PROSE_PLAN_v0.1.md` | 271 lines · 2836 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` | 424 lines · 4516 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/view-prose/VIEW_PROSE_PLAN_v0.1.md`  ·  **Size:** 271 lines · 2836 words

```markdown
# View Prose — Implementation Plan (SDK-home)

**Version:** v0.1 (post-exploration; feeds the reflective update of the requirements)
**Date:** 2026-06-11
**Status:** Plan — ready to reflect back onto requirements
**Pairs with (the "what"):** `strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` §C (FR-PG-10/11/12, OQ-7) —
the consumer-owned contract. This doc is the SDK-home "how" for hand-off item #3.
**Tracked:** `strtd8/docs/SDK_QUICK_WINS_2026-06-10.md` #7.
**Module:** `src/startd8/view_codegen/` (+ `backend_codegen/` drift/header glue).

> **Reading order.** §0 is the code reality this plan rests on (every claim file:line-cited). §1 is the
> one decision that matters — *where prose lives* — and why the requirements' implied answer was wrong.
> §6 is the accidental-complexity ledger (what we opportunistically fix vs. deliberately leave). §8 is
> the reflection that flows back into the requirements.

---

## 0. Code-grounded findings (the reality the plan rests on)

All verified by reading `view_codegen/` + `backend_codegen/` at HEAD.

### 0.1 The parser is already strict — adding a section is well-trodden
- `parse_views()` (`view_codegen/manifest.py:187-456`) is **loud-fail**: unknown view keys → `ValueError`
  (`:216-218`), unknown kind/scope/entity/field/compute-binding all raise. Allowed view key-set is the
  closed `_VIEW_KEYS` (`manifest.py:91-95`).
- Per-archetype key-sets are **already enforced and tight**: `import-flow` allows **only**
  `{name, kind, route}` (`:258-267`); `computed-panel` only `{name, kind, route, compute}` (`:269-285`);
  `rendered-content` only `{name, kind, route, root, content_field, prose_key}` (`:288-312`).
- Precedents for a *new strict section* are uniform and copyable: `parse_ai_passes`
  (`ai_layer.py:155-254`, `_PASS_KEYS`), `parse_pages` (`pages_generator.py:67-123`, `_PAGE_KEYS`),
  `parse_filters` (`filters_manifest.py:26-51`, `_KEYS`), `parse_forms` (`forms_manifest.py:35-72`).
  All raise `ValueError`; CLI catches it centrally (`cli_generate.py:267-271`). Closed-vocabulary
  reject-loud already exists (`parse_forms` `on_create`, `forms_manifest.py:66-70`).

### 0.2 The drift hash is whole-text — "outside the hash on the same file" is NOT free
- Owned files carry a 2- or 3-hash header (`_headers.py`); the hash is `schema_sha256(<entire input>)`
  — a plain SHA-256 of the **full text** (`schema_renderer.py:234-236`). `_check_forms_drift` hashes
  the **whole `views.yaml`**: `schema_sha256(forms_text)` (`drift.py:521`). **There is no
  subset-of-keys hashing anywhere in the codebase.**
- The proven "prose outside the hash" pattern is **architectural separation, not selective hashing**:
  - **pages:** owned shell `app/templates/pages/<name>.html` carries the header + `{% include %}`s an
    **untracked** body fragment `_<name>.body.html` that has **no header** and is re-rendered every
    run (`pages_generator.py:185-217`). Editing the source `.md` only rewrites the fragment → drift
    never trips. Header docstring states this explicitly (`_headers.py:65-85`).
  - **ai-layer:** the per-pass prompt lives in `app/ai/passes/<name>.md`, **read at generate time but
    never hashed** (`ai_layer.py:1-10`).
- **Consequence:** putting a hash-exempt `prose:` block *inside* `views.yaml` would force a new
  `parse-and-hash-only-the-structural-subset` mechanism (strip `prose:`, re-dump, hash) that **exists
  nowhere** and **diverges from every generator**. That is textbook accidental complexity. (See §1.)

### 0.3 The four archetypes render very unevenly — "give all four a title/intro" is not uniform
| Archetype | Renders an HTML page? | Title today | Outcome copy surface |
|---|---|---|---|
| `detail-compose` | **Yes** (`<h1>{v.module}</h1>`, `renderers.py:1053/1063`) | raw `name` | none (display-only) |
| `computed-panel` | **Yes** (`<h1>{v.module}</h1>`, `renderers.py:1071`) | raw `name` | none (display-only) |
| `import-flow` | **Yes** (`<h1>{v.module}</h1>` + 2 forms, `renderers.py:1077-1093`) | raw `name` | **JSON only** — validate/restore return JSON (`renderers.py:892-920`); **no server-side HTML success/error today** |
| `export-package` | **No** — template is a placeholder; routes serve raw JSON/Markdown (`renderers.py:820-837`) | n/a | n/a |

- **import-flow controls** are mostly **anonymous**: `<button>Validate</button>` / `<button>Restore</button>`
  carry **no `id`/`name`** (`renderers.py:1084/1090`). The file inputs (`name="file"`) and confirm
  checkbox (`name="confirm" value="restore"`) **are** stable (`:1083/1087/1088`). The control set is a
  **closed, tiny, per-archetype enum** (import-flow = validate/restore/confirm) — not an open space.
- **export-package has no HTML screen at all** — so FR-PG-11's "title/intro for `/export`" has *nowhere
  to render* without first adding an HTML landing surface to the archetype (new, separable scope).

### 0.4 Real computed values (corrects the v0.4 placeholder vocabulary)
| Archetype | Function | Returns | Real tokens |
|---|---|---|---|
| import-flow validate | `_validate` (`renderers.py:522-547`) | `{valid, errors, counts}` | `{errors}` (list), `{counts}` (per-entity) |
| import-flow restore | `_restore` (`renderers.py:561-584`) | `{imported, total}` | `{imported}` (per-entity), `{total}` (int) |
| computed-panel | `_data` (`renderers.py:341-349`) | `{score, nudges, present}` | `{score}` (0-1), `{present}` (per-entity); `nudges` already rendered |
| export-package | json/markdown (`renderers.py:618-666`) | raw export | **none** (no HTML outcome) |
| detail-compose | `_data` (`renderers.py:238-280`) | per-root list | **none** (display-only) |

- v0.4's vocabulary was wrong in three places: import-flow **success** is `{imported}`/`{total}` (not
  `{counts}`); export-package has **no** `{formats}` token (and no outcome surface); computed-panel is
  `{score}`/`{present}`, there is **no `{total}`**. **Outcome copy (`success`/`error` + any placeholder)
  applies to exactly ONE archetype: import-flow** — and even there it has no HTML rendering surface today.

### 0.5 Pre-existing prose infrastructure (naming-collision flag)
- `view_codegen` **already has a `prose_*` vocabulary** for a *different* thing: the `rendered-content`
  archetype (AR-6) renders an **entity's text column** as HTML via `prose_body`/`prose_preview`/
  `prose_html` (the `_PROSE_MODULE` string, `renderers.py:397-430`), keyed by the existing **`prose_key`**
  view key (`manifest.py:91`). That is *entity-data prose*, not *view-chrome copy*. Overloading the bare
  word "prose" for both is a cognitive-complexity risk (§6, AC-flag-5).

---

## 1. The one decision that matters: where prose lives

**Decision: a separate, strict-parsed `view_prose.yaml`, rendered into untracked fragments — NOT a
`prose:` section inside `views.yaml`.**

This is the essential-complexity choice, and it is forced by §0.2:

| Option | Hash-exemption mechanism | New code | Diverges from existing generators? |
|---|---|---|---|
| **A — `prose:` inside `views.yaml`** | strip `prose:` before hashing → hash structural subset | a *new* subset-hash path nobody else uses | **Yes** — every generator hashes whole text |
| **B — separate `view_prose.yaml` + untracked fragment** *(CHOSEN)* | prose is a *different file*, read at generate time, rendered to a header-less fragment the owned template `{% include %}`s | **zero new hashing code** — reuses the pages mechanism verbatim | **No** — identical to pages + ai-layer |

Option B is also the *consistent* SDK pattern, confirmed by the display layer's own history: **hash-exempt
prose → standalone file; hashed structural config → `views.yaml` sections.** `display.yaml` shipped
**standalone** (not a `views.yaml` section) precisely because the team converged on file-per-lifecycle;
`filters:`/`forms:` are `views.yaml` sections *because they are structural/hashed*. Prose, being
hash-exempt, belongs in its own file by the same rule. This **retires the v0.4 ambiguity** (which named
both `views.yaml prose:` and a parked `prisma/view_prose.yaml`) in favor of the one that costs nothing.

**Rendering mechanism (mirror `pages_generator.py:185-217` exactly):**
1. The **owned view template** keeps its schema+views 2-hash header and its structural body, but its
   title/intro/empty slots become `{% include %}` of a prose fragment (or fall back to a literal when no
   fragment exists).
2. The **prose fragment** (`app/templates/views/_<name>.prose.html` — header-less, untracked) is
   rendered from `view_prose.yaml` at generate time and overwritten every run.
3. Editing `view_prose.yaml` rewrites only the fragment → `--check` on the owned template stays green.
   **No prose hash exists at all** (same as ai-layer prompts).

---

## 2. Phasing (sharper than v0.4)

§0.3/0.4 force a cleaner cut than v0.4's "everything but controls is Phase 1":

- **Phase 1 — static chrome, zero substitution, zero new render surface.** Keys `title`, `intro`,
  `empty`. Pure text rendered into the untracked fragment. Lands on the three archetypes that *already
  render HTML* (detail-compose, computed-panel, import-flow). **No placeholder engine, no control ids,
  no new endpoints.** This is the bulk of the user-visible win ("no screen shows a raw machine name").
- **Phase 2 — gated, because each needs a new render surface:**
  - `controls` labels — needs the two anonymous import-flow buttons to get **stable `id`s** first
    (trivial, but sequenced). Control set is the closed enum `{validate, restore, confirm}`.
  - `success`/`error` + placeholders — **import-flow only**, and needs an **HTML outcome surface**
    (today validate/restore return JSON; there is nowhere to render copy). Placeholder set is closed:
    validate→`{errors}`/`{counts}`, restore→`{imported}`/`{total}`.
  - `export-package` title/intro — needs an **HTML landing surface** added to the archetype first
    (today it serves only JSON/Markdown). Separable archetype enhancement; not blocking Phase 1.

> v0.4 had `success`/`error` in Phase 1. Planning moves them to Phase 2: there is **no HTML surface**
> to render outcome copy into, and they touch exactly one archetype. Shipping title/intro/empty first
> delivers ~all of the visible value with none of the surface-area risk.

---

## 3. Implementation steps (Phase 1)

| # | Step | File(s) | Notes |
|---|---|---|---|
| S1 | `parse_view_prose(text, *, known_views) -> dict[str, ViewProse]` | **new** `view_codegen/view_prose.py` | Copy `parse_pages`/`parse_filters` shape: `ValueError` loud-fail; `_PROSE_KEYS = {"title","intro","empty"}` (Phase 1); reserved set `{"controls","success","error"}` **rejected-loud** until Phase 2 (the `parse_forms` reserved pattern); gate view names against `known_views`. |
| S2 | `ViewProse` dataclass (`title/intro/empty: str|None`) + `__init__` re-export | `view_codegen/view_prose.py`, `view_codegen/__init__.py` | Keep ViewSpec untouched — prose is a *sidecar* keyed by view name, not a field on ViewSpec (preserves the views.yaml hash surface). |
| S3 | Render the untracked prose fragment per view | `view_codegen/renderers.py` (new `render_view_prose_fragment`) | Mirror `render_page_body_fragment` (`pages_generator.py:210-217`): header-less HTML partial, overwritten each run. |
| S4 | Owned templates `{% include %}` the fragment with literal fallback | `renderers.py` archetype templates (`:1053/1063/1071/1081`) | Replace `f"<h1>{v.module}</h1>"` with a Jinja slot: `<h1>{% block vtitle %}{module}{% endblock %}</h1>` overridden by the fragment include; intro/empty likewise. **Touch only the title/intro/empty lines** — not the dispatch or data code. |
| S5 | Header kind + drift routing for the owned view templates | `_headers.py`, `backend_codegen/drift.py` | The owned view template already needs a views-hash header; ensure the **fragment** carries none and is excluded from `--check` (it is, by having no `startd8-artifact` marker — `drift.is_owned_view_file`). |
| S6 | CLI flag `--view-prose prisma/view_prose.yaml` + cap-dev-pipe pass-through | `cli_generate.py` | Mirror `--pages`. Absent ⇒ today's behavior (literal fallback). |
| S7 | Tests | `tests/unit/view_codegen/test_view_prose.py` | parse loud-fail (unknown key, unknown view, reserved key present); fragment render; **drift-stability test: edit prose → `--check` stays in_sync** (the load-bearing guarantee); literal fallback when absent. |

**Backward-compat invariant (test it):** with no `view_prose.yaml`, every owned template renders
**byte-identical** to today (literal `{module}` fallback) — the `filters:`/`forms:` "inert when absent"
contract (`filters_manifest.py:30-32`).

---

## 4. Implementation steps (Phase 2 — gated, listed for completeness)
- P2a: add stable `id`s to import-flow buttons (`renderers.py:1084/1090`), enumerate the closed control
  set, extend `_PROSE_KEYS` with `controls`, render labels from the fragment.
- P2b: add an HTML outcome surface to import-flow (render validate/restore result server-side or via a
  small htmx swap), then enable `success`/`error` with the closed placeholder set + a *whitelist*
  substitution (renderer substitutes only known tokens; unknown `{x}` → loud parse error).
- P2c: add an HTML landing template to `export-package` (intro + the two format download links), then
  enable its `title`/`intro`.

---

## 5. Placeholder vocabulary — corrected & closed (for Phase 2)
- **import-flow** — `error`: `{errors}`, `{counts}` · `success`: `{imported}`, `{total}`.
- **computed-panel / detail-compose / export-package** — **no outcome copy, no placeholders.**
- Substitution is a **whitelist** keyed by `(archetype → token set)`; an unknown `{token}` is a loud
  parse error. No general template-eval — just `str.replace` over the closed set. (Essential complexity:
  one archetype, four tokens; do **not** build a substitution engine.)

---

## 6. Accidental-complexity ledger (the user's explicit ask)

**Opportunistically eliminate (we're touching these lines anyway, low risk):**
- **AC-1 — f-string titles → Jinja slot.** `f"<h1>{v.module}</h1>"` repeated at `renderers.py:1053/
  1063/1071/1081/966/1054` blocks any per-view title injection. Converting *just the title/intro/empty
  lines* to Jinja blocks (S4) is the cleaner substrate and removes the "title is hardcoded in Python"
  smell. Scope-limited to those lines.
- **AC-2 — scattered empty-state literals.** "not yet linked" (`:1048`), "Nothing here yet" (`:967/
  1026`), "All signals met." (`:1074`), "No {root} records yet" (`:1054`) are duplicated copy baked in
  renderers. Route them through the prose `empty` key **with the current string as the literal default**
  — no behavior change when prose absent, but now overridable and centrally visible.

**Deliberately DO NOT touch (flagged for a future, separate pass — touching them now is scope creep):**
- **AC-3 — mixed dispatch** in `render_view_module` (`renderers.py:736-753`): special-cases +
  `_MODULE_RENDERERS` table. A `(kind, scope)` dispatch table would be cleaner, but it is **not on the
  prose path** — refactoring it now adds risk for no prose benefit. *Flag only.*
- **AC-4 — `_PROSE_MODULE` as a baked string literal** (`renderers.py:397-430`): should be a real `.py`
  imported, not a `"\n".join` string. Orthogonal to view-chrome prose. *Flag only.*
- **AC-5 — "prose" overload** (§0.5): existing `prose_key`/`prose_body` (entity-data prose) vs. new
  view-chrome copy. **Mitigation chosen:** the new input is a *separate file* `view_prose.yaml` and the
  new dataclass is `ViewProse` (chrome), keeping the existing `prose_key` (rendered-content) untouched.
  Residual English-overload accepted; **do not** rename the existing `prose_*` helpers (churn for no
  gain). *Documented, contained.*
- **AC-6 — label fallback split** (`renderers.py:972` template chain vs `:247/259` data binding):
  pre-existing inconsistency in the *display* layer, not the prose layer. *Flag only.*
- **AC-7 — test-scaffold duplication** (`renderers.py:1165-1508`): real, but a test-infra refactor, not
  prose. *Flag only.*

**Net:** the prose feature *adds* one small module + one fragment-render path (both copies of proven
patterns) and *removes* the hardcoded-title and scattered-empty-state smells on the exact lines it
touches. It introduces **zero** new hashing, dispatch, or substitution machinery in Phase 1.

---

## 7. Risks
- **R1 — fragment-include must be header-less & marker-less** or `--check`/`is_owned_view_file` will try
  to drift-check it. Mitigation: render with no `startd8-artifact` marker (S5); cover with the
  drift-stability test (S7).
- **R2 — export-package & success/error look like Phase 1 in the requirements but have no render
  surface.** Mitigation: §2 moves them to Phase 2 explicitly; requirements update must match.
- **R3 — naming overload (AC-5)** could confuse future readers. Mitigation: separate file + `ViewProse`
  type + a one-line note in `manifest.py` distinguishing `prose_key` (entity content) from
  `view_prose.yaml` (view chrome).

---

## 8. Reflection → what flows back to the requirements (v0.4 → v0.5)

| v0.4 assumption | Planning discovery | Requirement impact |
|---|---|---|
| Prose is a `prose:` **section of `views.yaml`**, kept outside the drift hash (FR-PG-10/12) | The whole `views.yaml` is hashed (`drift.py:521`); subset-hashing exists nowhere. Hash-exemption is achieved **only** by a separate file + untracked fragment (pages/ai precedent) | **Reframe FR-PG-10/12:** prose lives in a standalone **`view_prose.yaml`**, rendered into an untracked fragment. Drop the "section of views.yaml" framing. Net **less** complexity. |
| `success`/`error` ship in Phase 1 on all four archetypes (v0.4) | Outcome copy is **import-flow-only** and has **no HTML render surface** today; export-package renders **no HTML page** at all | **Re-phase:** Phase 1 = `title`/`intro`/`empty` on the 3 HTML archetypes. `success`/`error` and export-package title/intro → **Phase 2** (each needs a new render surface). |
| Placeholder set: import-flow `{counts}`/`{errors}`, export `{formats}`, panel `{score}`/`{total}` | Real: import-flow success = `{imported}`/`{total}`; export has **no** tokens/surface; panel = `{score}`/`{present}`, no `{total}` | **Correct FR-PG-10** vocabulary; mark it Phase-2 (import-flow only). |
| OQ-7: "can view_codegen expose stable enumerable control_ids?" (open feasibility) | Controls are a **closed tiny enum**, currently anonymous; making them stable is a ~2-line change | **OQ-7 downgrades** from "unknown feasibility" to "known-trivial, sequenced." Resolve it; keep `controls` Phase-2 for *sequencing*, not risk. |
| (not seen) | `view_codegen` already uses `prose_key`/`prose_body` for **entity-data** prose | **Add a non-requirement / note:** new view-chrome prose is a distinct layer; separate file + `ViewProse` type avoids the overload. |
| Strict-parse is a fresh contract to define | Four copyable precedents (`parse_ai_passes`/`parse_pages`/`parse_filters`/`parse_forms`), all `ValueError`, reserved-key reject already exists | **Strengthen FR-PG-10** to name the precedent (`parse_pages` shape) so the contract is unambiguous and the reserved-key Phase-2 gate is a known pattern. |

---

*v0.1 — Initial plan from `view_codegen/` exploration. Central finding: prose must be a **separate
file rendered to an untracked fragment** (not a `views.yaml` section) — the only hash-exempt mechanism
the codebase supports, and it costs zero new machinery. Phase 1 narrowed to `title`/`intro`/`empty`;
`success`/`error`/`controls`/export-landing moved to Phase 2 (each needs a new render surface).
Placeholder vocabulary corrected against real computed values. Accidental-complexity ledger in §6.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/strtd8/strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md`  ·  **Size:** 424 lines · 4516 words

```markdown
# StartDate User-Facing Content — Requirements

**Version:** 0.5 (Post-planning reframe — prose moves to a standalone `view_prose.yaml`; Phase 1 narrowed)
**Date:** 2026-06-11 (v0.5, v0.4) · 2026-06-10 (v0.3) · 2026-06-03 (v0.2)
**Plan (the "how"):** `startd8-sdk/docs/design/view-prose/VIEW_PROSE_PLAN_v0.1.md` — the SDK-home
implementation plan whose code-grounded findings drove this v0.5 reflective update.
**Status:** Draft (ready for review)
**Owner (this doc):** `startd8` consumer repo · **Generator capability:** `startd8-sdk` (SDK-home, to be ratified)
**Related:** `docs/REQUIREMENTS.md` (product purpose, FR-9/FR-11), `CLAUDE.md` (product overview),
`docs/AI_LAYER_GENERATION_TEAM_UPDATE.md` (the `ai_passes.yaml` precedent), `IDEAL_TARGET_ARCHITECTURE.md`,
`docs/SDK_QUICK_WINS_2026-06-10.md` (the SDK capability this needs).
**Complements (do not duplicate):** the **structure** layer — **`prisma/display.yaml`** (SHIPPED
2026-06-10, SDK FR-DM-1..7): entity list columns/labels/order, detail sections, row `label_field`, and
composite-view FK label resolution (`root_label_field` + relation `via_fk`/`label_field`). **This doc owns
the *words*; `display.yaml` owns the *structure*.** They meet on the composite views with zero key overlap:
the **words here** (titles/intros/empty + relation headings, authored in a standalone **`prisma/view_prose.yaml`**
— v0.5; *not* a section of `views.yaml`, see §0.5/FR-PG-10) are authored/outside-the-hash; the **bindings
in `display.yaml`** (which field resolves a row to a name) are
regenerate/inside-the-hash. The `/value-map` rows + group headings already read as names (display.yaml
binding live); the view `<h1>` + relation headings stay raw until **this doc's** view-prose (#7) ships. The
`/value-map` copy below targets the **`value_map_overview`** view (model-scoped, `/value-map`), not
`value_map` (`/value-map/{id}`).

> **What changed in 0.5 (2026-06-11, post-planning reflective update).** An SDK-home planning pass
> against `view_codegen/` (plan doc linked above) read the actual code and overturned two v0.4
> assumptions — the loop working as intended:
> 1. **Prose moves OUT of `views.yaml` into a standalone `view_prose.yaml`.** The SDK hashes the
>    *entire* `views.yaml` text (no subset-of-keys hashing exists anywhere), so a hash-exempt `prose:`
>    *section* would force a brand-new subset-hash mechanism = accidental complexity. The proven,
>    zero-new-code path for "prose outside the hash" is a **separate file rendered into an untracked
>    fragment** (exactly how `pages.yaml`→`*.md` and `ai_passes.yaml`→`*.md` already work). This is
>    *less* complex, and it matches the SDK's own pattern (`display.yaml` shipped standalone too).
> 2. **Phase 1 narrows to `title`/`intro`/`empty`.** `success`/`error` apply to **import-flow only** and
>    have **no HTML render surface** today; `export-package` renders **no HTML page** at all. So those
>    (and `controls`) move to **Phase 2**, each gated on a new render surface, not just on OQ-7.
>    Placeholder vocabulary corrected against real computed values (see FR-PG-10). §A/§B unchanged.
>
> **What changed in 0.4 (2026-06-11, pre-build review).** §C (View prose) is hardened, not expanded:
> the `prose:` key-set is **phased** — `title`/`intro`/`empty`/`success`/`error` are buildable now;
> `controls:` is **reserved-until-built** behind OQ-7 (which resolves the v0.3 graceful-vs-loud-fail
> contradiction). The `success`/`error` **placeholder set is now closed per archetype** (unknown
> `{placeholder}` = loud parse error). The `/completeness` per-signal nudges are documented as an
> **archetype-owned exception** (not a prose key). §A/§B unchanged. See changelog at the foot.
>
> **What changed in 0.3 (2026-06-10).** v0.2 gave the app a *shell* (home, how-it-works, nav) and
> entity-**form** blurbs (FR-PG-3), all shipped. But the generated **composite-view archetypes** —
> `import-flow` (`/import`), `export-package` (`/export`), `computed-panel` (`/completeness`),
> `detail-compose` (`/value-map`) — still render the **raw view name** as a title (e.g. a page
> literally headed "model_import" with two unlabeled file pickers and a bare "Validate"/"Restore")
> with **no explanation, no control labels, and no success/empty/error copy**. v0.3 adds the
> **View-prose grammar** (FR-PG-10) and applies it to those four archetypes (FR-PG-11), keeping the
> prose **authored + outside the drift hash** (the FR-PG-7 precedent). The SDK `view_codegen`
> capability that consumes it is **verify-at-home** (hand-off §5; tracked in SDK_QUICK_WINS #7).
> Scope stays "basic to start" — semantic HTML, no theming.

> **Boundary (tekizai-tekisho).** This repo owns the *content/UX spec* and the *manifest contract*
> (`pages.yaml` + nav) below. The *generator capability* that consumes them is `startd8-sdk` work,
> to be ratified by an SDK-home agent. SDK mechanism claims here are `verify-at-home`.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2 (post-planning). A planning pass against the
> `startd8-sdk` generator (`backend_codegen/`) resolved all six open questions and reframed one
> requirement. SDK citations are `verify-at-home`.

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| "Hide system fields" might need a new `human_inputs.yaml` extension (FR-PG-5) | The SDK **already** computes the system/provenance/timestamp omission set (`ai_layer.py:_PROVENANCE_OMIT` + "drop ids/provenance/timestamps", :286–320) — but applies it only to the **AI edge schema**, not the **HTMX form generator** | **FR-PG-5 reframed**: not a new policy — *reuse the existing omission in the form generator*. And **split out** as a separate SDK forms-fix contract, not a `pages.yaml` requirement |
| `pages.yaml` shape was loosely sketched | `ai_passes.yaml` is parsed **strictly**: fixed key-set, required keys, **loud failure on unknown keys** (`ai_layer.py:95–107`) | **FR-PG-6 tightened** to the same strict-parse contract (exact allowed keys, loud-fail) |
| Root/content route home unknown (OQ-5) | Routes mount via `web_router`/`all_routers` in `main.py` (`htmx_generator.py:282`, `crud_generator.py:183`) | Content pages fit cleanest as a **parallel generated `app/pages.py` + `pages_router`**, mounted alongside `web_router` |
| `base.html` nav injection unknown (OQ-6) | `base.html` is a **hardcoded string literal** (`htmx_generator.render_base_template`) — no seam | Nav requires an **SDK generator change** to emit `<nav>` from the manifest; no new templating engine needed |

**Resolved open questions:**
- **OQ-1 → mirror the strict parser.** `pages.yaml` = top-level `pages:` list, fixed key-set, required keys, loud-fail on unknowns (parallel to `parse_ai_passes`).
- **OQ-2 → derived nav with optional override.** Default: nav built from pages that declare `nav_label` + a curated entity subset; allow an explicit `nav:` list to override/order. Avoids hand-maintaining links.
- **OQ-3 → form-generator fix (reuse existing omission).** See FR-PG-5 reframe above. Not `pages.yaml`, not `human_inputs.yaml`.
- **OQ-4 → markdown files, prose outside the hash.** `app/pages/*.md` authored; route/template/nav generated. Editing prose must not trigger drift (mirror the ai-passes prompt rule).
- **OQ-5 → new `app/pages.py` + `pages_router`** mounted in `main.py`/`server.py`.
- **OQ-6 → SDK generator change to `base.html`** (emit nav); no consumer hand-edit (would drift).

---

## 1. Problem Statement

StartDate's generated app today is **CRUD pages with no shell**: no landing page, no navigation, no
explanation of what the app is or how to use it. A first-time user lands on `localhost:8765` and gets
`{"detail":"Not Found"}`. The product purpose (articulate your value to land a start date; Command of
the Message kept invisible) exists only in *developer* docs, never surfaced to the user.

| Component | Current state | Gap |
|---|---|---|
| Root `/` | 404 (no route) | No home/landing page |
| Navigation | `base.html` is bare (`<title>` + htmx + `<main>`); no nav | No way to move between Profile / ProofPoints / value map |
| Purpose / how-it-works | Only in `REQUIREMENTS.md`, `CLAUDE.md` (developer docs) | No user-facing explanation |
| Form usability | `profile/form.html` exposes `id`, `ownerId`, `source`, `confirmed`, `createdAt`, `updatedAt` as **required**, labeled with raw field names | Users asked to hand-type a CUID + timestamps; forms are unusable + unexplained |
| Generation mechanism | SDK generates only entity-CRUD + AI-passes; no content-page capability | A new owned-generation input is needed (no hand-authoring — drift) |

**Goal:** define a *basic*, owned-generation path for a home page, a purpose/how-it-works page, and
form guidance — produced by the SDK/pipe from a manifest, not hand-written.

---

## 2. Requirements

### A. Content & UX (consumer-owned "what")

- **FR-PG-1 — Home/landing page at `/`.** A root route renders a landing page: one-line product
  promise, a short "what this is", and primary calls-to-action linking to the first step (Profile) and
  to the how-it-works page. Replaces the current 404.
- **FR-PG-2 — Purpose / "How StartDate works" page.** A static content page explaining, in
  user-language: what StartDate helps you do (articulate your value to land a start date), the basic
  flow (add Profile + accomplishments → the app enriches them → review/confirm → generate a value
  summary + pitches → export), and the fast-vs-deep choice (FR-11) + completeness nudge (FR-9). The
  Command-of-the-Message methodology stays **invisible** (no jargon surfaced).
- **FR-PG-3 — Basic form guidance.** Each primary entity form (Profile, ProofPoint to start) shows a
  one-or-two-sentence purpose blurb and human-readable field labels/help, so a user knows what to enter
  and why.
- **FR-PG-4 — Navigation shell.** A persistent nav (in `base.html`) links the key destinations: Home,
  Profile, ProofPoints, the value map (ValueProps), and How-it-works. Present on every page.
- **FR-PG-5 — Forms must not demand system/provenance fields.** *(SEPARATE SDK CONTRACT — surfaced
  here because it's the precondition that makes FR-PG-3 meaningful, but it is **not** a `pages.yaml`
  concern.)* The HTMX form generator must omit `id`, `ownerId`, `source`, `confirmed`, `createdAt`,
  `updatedAt` from entity forms (auto-managed), exposing only human-authored fields with
  human-readable labels. **Planning found the SDK already computes this omission set** for the AI
  edge schema (`ai_layer.py` `_PROVENANCE_OMIT` + ids/provenance/timestamps drop); the fix is to
  **reuse it in the form generator** (`htmx_generator.py`) — a small SDK-home change, tracked
  separately from this content-pages contract. Acceptance: `profile/form.html` shows only
  `name/title/company/...`, never `id`/`ownerId`/`createdAt`.

### B. Manifest contract (consumer-owned input the SDK consumes)

- **FR-PG-6 — `pages.yaml` manifest (strict-parse, mirrors `ai_passes.yaml`).** A new declarative
  input. Parsing MUST follow the proven `parse_ai_passes` contract (`ai_layer.py:95–107`): a mapping
  with a top-level `pages:` list; each entry a mapping with a **fixed allowed key-set**; **required
  keys enforced**; **unknown keys → loud failure** (no silent drops). Allowed per-page keys (draft):
  `slug` (req), `title` (req), `nav_label` (opt — omit to exclude from nav), `content` (req — path to
  a markdown file under `app/pages/`). Optional top-level `nav:` list (see FR-PG-4 / OQ-2).
  ```yaml
  pages:
    - slug: "/"
      title: "StartDate"
      nav_label: "Home"
      content: pages/home.md            # markdown under app/pages/
    - slug: "/how-it-works"
      title: "How StartDate works"
      nav_label: "How it works"
      content: pages/how_it_works.md
  nav:                                  # optional; else derived from nav_label + curated entities
    - {label: "Home", href: "/"}
    - {label: "Profile", href: "/ui/profile"}     # NOTE: the human HTML page is /ui/<entity>
    - {label: "How it works", href: "/how-it-works"}
  ```
  > **POC-confirmed routing fact:** the human-facing HTML pages live under **`/ui/<entity>`**
  > (`/ui/profile`, `/ui/proofpoint`, …); the bare `/<entity>/` route returns **JSON** (the CRUD API).
  > Nav/CTA links MUST target the `/ui/...` family. If nav is auto-derived from entities, it must use
  > the `/ui/` route prefix, not the API prefix.
- **FR-PG-7 — Markdown content is authored, glue is generated.** The page *prose* lives in
  `app/pages/*.md` (consumer-authored, like AI prompts are the only authored AI-layer surface). The
  *route + template + nav* are generated/owned. Editing prose must NOT trigger drift (mirror the
  ai-passes rule: prompt content is outside the hash).
  **Rendering (POC-confirmed):** markdown→HTML SHOULD be rendered at **generate time** into the owned
  template, NOT at request time. The POC rendered at request time and had to add a `markdown` runtime
  dependency; generate-time rendering keeps the app runtime dependency-free and consistent with the
  static owned-generation model. *(Open: do MD edits then require a regen to take effect? Acceptable —
  same as any owned artifact; or watch/render-on-boot. Recommend regen, keeps one drift model.)*
- **FR-PG-8 — Owned + drift-tracked.** Generated page routes/templates and the updated `base.html`
  carry the three-hash header and participate in `--check`. Inputs (`pages.yaml`, `app/pages/*.md`)
  get anchored in `upstream-anchors.txt`.
- **FR-PG-9 — Pipe-consumable.** The cap-dev-pipe `--lang python` flow and the direct
  `startd8 generate backend` command both accept the new input (e.g. `--pages prisma/pages.yaml`)
  with no change to the owned-spine protection model.

### C. View prose (v0.5 — composite-view archetypes get end-user copy, from a standalone manifest)

> **0.5 reframe (why a separate file).** v0.3/0.4 proposed a `prose:` *block inside `views.yaml`*, kept
> outside the drift hash. Planning against `view_codegen/` found the SDK hashes the **whole `views.yaml`
> text** — there is no subset-of-keys hashing anywhere — so a hash-exempt section would need new,
> divergent machinery. Instead, prose lives in a **standalone `view_prose.yaml`** (mirroring
> `ai_passes.yaml`), rendered into an **untracked fragment** the owned view template `{% include %}`s.
> This is the *only* hash-exempt path the codebase already supports (the `pages.yaml`→`*.md` mechanism),
> costs **zero new hashing code**, and matches the SDK's own convention (hashed structural config →
> `views.yaml` sections like `filters:`/`forms:`; hash-exempt prose → its own file, like `display.yaml`
> shipped standalone). Same discipline as FR-PG-7: prose authored, outside the drift hash, editing it
> never forces a logic regen.

- **FR-PG-10 — `view_prose.yaml` manifest (strict-parse, mirrors `pages.yaml`/`ai_passes.yaml`).** A new
  standalone input keyed by **view name**, each entry a mapping with a **fixed allowed key-set**
  (strict-parse, `ValueError` loud-fail on unknown keys / unknown view names — the exact
  `parse_pages`/`parse_ai_passes` contract). Absent ⇒ today's behavior (fall back to the view `name`).
  The key-set ships in **two phases**, cut by *whether the SDK already has a render surface for the
  key* (planning finding — see plan §0.3/§2):

  **Phase 1 — static chrome (buildable now; no substitution, no new render surface).** All optional:
  - `title` — the human page heading (replaces the raw `name`, e.g. "Restore from a backup").
  - `intro` — a short markdown paragraph under the title: what this screen is for, in user language.
  - `empty` — copy shown when there's nothing to show yet (no file chosen, no data). Replaces today's
    scattered hardcoded empty-state literals ("not yet linked", "Nothing here yet", …) — the existing
    string becomes the default when `empty` is absent.

  Phase 1 lands on the **three archetypes that already render an HTML page** — `detail-compose`
  (`/value-map`), `computed-panel` (`/completeness`), `import-flow` (`/import`). It is pure static text
  rendered into the untracked fragment: **no placeholder engine, no control-ids, no new endpoints.**

  **Phase 2 — keys that each need a NEW render surface first (gated; not just on OQ-7):**
  - `success` / `error` — outcome copy. **Applies to `import-flow` only** (the other archetypes have no
    outcome action). Today validate/restore return **JSON**, so there is **no server-side HTML surface**
    to render this copy into — Phase 2 must add one. Placeholder set is **closed and corrected against
    the real computed values** (renderer substitutes a whitelist; unknown `{placeholder}` = loud parse
    error; *not* a general template engine):
    - `import-flow` `error` (validate) → `{errors}` (list), `{counts}` (per-entity)
    - `import-flow` `success` (restore) → `{imported}` (per-entity), `{total}` (int)
    - *(v0.4 errata: success is `{imported}`/`{total}`, **not** `{counts}`; `export-package` has no
      `{formats}` token and no HTML outcome surface; `computed-panel` is `{score}`/`{present}`, there is
      no `{total}`. Corrected here.)*
  - `controls` — a mapping of `control_id → { label, help }` for an archetype's buttons. **import-flow's
    Validate/Restore buttons are anonymous today** (no `id`/`name`); the control set is a **closed tiny
    enum** (`validate`/`restore`/`confirm`) the SDK must first stamp with stable ids (OQ-7 — now
    *known-trivial*, sequenced for discipline). Rejected-loud if present until built.
  - `export-package` `title`/`intro` — `/export` renders **no HTML page** today (it serves raw
    JSON/Markdown). Giving it a title/intro requires **adding an HTML landing surface** to the archetype
    first (a small download page). Separable enhancement; not in Phase 1.

  > **Naming note (SDK-internal).** `view_codegen` already uses `prose_key`/`prose_body` for a *different*
  > layer — rendering an entity's text *column* as HTML in the `rendered-content` archetype. The new
  > view-**chrome** copy here is a distinct concern; the standalone `view_prose.yaml` + a `ViewProse`
  > type keep them from colliding. (Verify-at-home; plan §0.5/AC-5.)

  Prose values are short markdown; long prose MAY instead point at a markdown file under
  `app/pages/` (path string), exactly like content pages (FR-PG-7), so heavier copy lives in `.md`.
  The example below is the **standalone `prisma/view_prose.yaml`**, keyed by view name. Phase-1 keys
  (`title`/`intro`/`empty`) are authorable now; the `controls`/`success`/`error` keys are **Phase 2** —
  shown for shape, not yet authorable.
  ```yaml
  # prisma/view_prose.yaml — consumed by `generate views --view-prose …`; outside the drift hash.
  # Strict-parse: unknown keys / unknown view names fail loud (parse_pages contract). Absent ⇒ raw name.
  model_import:                          # keyed by the view's machine name (matches views.yaml)
    title: "Restore from a backup"       # ── Phase 1 ──
    intro: |
      Bring back a value model you exported from StartDate. Pick a JSON file you exported here
      before. **Check this file** verifies it and changes nothing; **Restore** writes it in.
    empty: "No file chosen yet."
    # ── Phase 2 (not yet authorable — each needs a new SDK render surface) ──
    # controls:                          # needs stable control-ids (OQ-7)
    #   validate: { label: "Check this file", help: "A dry run — reports problems, writes nothing." }
    #   restore:  { label: "Restore my data", help: "Existing items update, new items add, none deleted." }
    #   confirm:  "Yes, write this into my database"
    # success: "Restored {imported} items ({total} total). Your value model is back."   # import-flow only
    # error:   "That file couldn't be read as a StartDate export — {errors}"            # import-flow only
  ```

- **FR-PG-11 — Apply View prose to the archetypes that render an HTML page.** Acceptance copy (the
  *what*, voice = plain, CoM stays invisible; final wording editable). **Phase 1 covers the three
  archetypes that already render HTML** (`detail-compose`, `computed-panel`, `import-flow`); the fourth
  (`export-package`) and all outcome/control copy are **Phase 2** (need a new render surface — FR-PG-10):
  - **`/value-map` (detail-compose) — Phase 1:** `title` "Your value map"; `intro` "How your proof
    points connect to the capabilities and outcomes they support — only the links you've confirmed are
    shown."; `empty` reuses "not yet linked" (today's literal becomes the default).
  - **`/completeness` (computed-panel) — Phase 1:** `title` "How complete is your value model?"; `intro`
    explains the score is **guidance, never a gate** (FR-9) and that **only confirmed items count**.
    **Exception (per §2 boundary):** the existing **per-signal nudge strings stay archetype-owned** (the
    panel emits them today) — **not** a prose key; FR-PG-10 has no per-signal-nudge grammar and adding
    one is out of scope. Only panel-level `title`/`intro`/`empty` are prose-owned.
  - **`/import` (import-flow, model_import) — Phase 1 (`title`/`intro`/`empty`) + Phase 2 (controls,
    success/error):** `title`/`intro` must make explicit this is **restoring your own StartDate export**
    (not importing a résumé — that's the Document Library), that **Validate writes nothing**, and that
    **Restore upserts and never deletes**. The Validate/Restore/confirm **control labels** and the
    restore **success/error** copy are **Phase 2** (anonymous buttons need stable ids; JSON outcomes
    need an HTML surface — FR-PG-10).
  - **`/export` (export-package) — Phase 2:** title "Export your value model" + intro ("Download
    everything you've built — profile, proof points, capabilities, outcomes, metrics, differentiators,
    value props — as Markdown (readable) or JSON (re-importable here).") require an **HTML landing
    surface** added to the archetype first (today `/export` serves only raw JSON/Markdown — no page to
    host the words). Deferred to Phase 2 as a small, separable archetype enhancement.

- **FR-PG-12 — Prose is owned-authored, outside the drift hash via a separate file + untracked
  fragment (mirrors `pages.yaml`/`ai_passes.yaml`).** `view_prose.yaml` is consumer-authored; the
  owned view template keeps its schema+views drift header and `{% include %}`s a **header-less,
  untracked prose fragment** the SDK re-renders every run. Editing `view_prose.yaml` rewrites only the
  fragment → **`--check` on the owned template stays green**; there is **no prose hash at all** (same as
  ai-layer prompts). Inputs anchored in `upstream-anchors.txt`.
  **Validation timing (clarification, not new machinery):** hash-exemption means prose is simply never
  hashed — but `view_prose.yaml` is still **strict-parsed at generate time** (FR-PG-10 loud-fail), so a
  bad key/placeholder is caught on the next `generate`, just not by `--check`. No separate
  prose-validation pass is added (deferred unless a real break demands it).
  **Backward-compat invariant:** with no `view_prose.yaml`, every owned template renders byte-identical
  to today (literal `name` fallback) — the `filters:`/`forms:` "inert when absent" contract.

---

## 3. Non-Requirements

- **No styling/theming system.** Plain semantic HTML + the existing inline-style convention; no CSS
  framework. "Basic to start." *(The baseline usability theme + layout/columns/labels are owned by the
  **structure** layer — `docs/v2/PRESENTATION_DISPLAY_REQUIREMENTS_v0.1.md` PD-13/PD-4/PD-7 — not here.
  That doc is where "no theming" gets an owner without violating this doc's copy-only scope.)*
- **No CMS / WYSIWYG / multi-page routing beyond the declared list.**
- **No auth, no multi-user, no i18n.** Local-first single-user is unchanged.
- **No rich onboarding wizard.** A static how-it-works page, not an interactive tour.
- **Not a redesign of the entity CRUD pages** beyond FR-PG-3/FR-PG-5 (labels/help, hide system fields).
- **View prose is copy, not layout (v0.3).** FR-PG-10/11 add explanatory text, control labels, and
  outcome copy to the composite views; they do **not** restructure an archetype's panels, controls,
  or data flow. A view with no `prose:` renders exactly as today.
- **The SDK implementation is out of scope for *this* doc** — it specifies the contract; the generator
  is SDK-home work.

---

## 4. Open Questions — all resolved by the planning pass (see §0)

- **OQ-1 — Manifest shape fidelity.** ✅ Resolved → mirror `parse_ai_passes` strict parsing (FR-PG-6).
- **OQ-2 — Nav: declared vs derived.** ✅ Resolved → derived from `nav_label` + curated entities, with
  an optional explicit `nav:` override (FR-PG-4).
- **OQ-3 — Where does hide-system-fields belong?** ✅ Resolved → a **form-generator fix** that reuses
  the SDK's existing provenance/timestamp omission set; **not** `pages.yaml`/`human_inputs.yaml`.
  Reframed as FR-PG-5, tracked as a separate SDK contract.
- **OQ-4 — Content source format.** ✅ Resolved → markdown files under `app/pages/`, prose kept
  outside the drift hash (FR-PG-7).
- **OQ-5 — Root-route integration seam.** ✅ Resolved → new generated `app/pages.py` + `pages_router`
  mounted alongside `web_router` in `main.py`/`server.py`.
- **OQ-6 — base.html nav injection.** ✅ Resolved → SDK generator change to emit `<nav>`; no new
  templating engine; no consumer hand-edit.
- **OQ-7 (v0.3 open → v0.4 phased → v0.5 RESOLVED) — control_id stability for `controls`.** Planning
  read the import-flow renderer: its controls are a **closed, tiny enum** (`validate`/`restore`/
  `confirm`), and the buttons are merely **anonymous today** (no `id`/`name`, `renderers.py:1084/1090`)
  — making them stable is a ~2-line template change. So the feasibility question is **answered: yes,
  trivially.** `controls` stays **Phase 2 for sequencing discipline, not technical risk** — it ships
  once the SDK stamps the ids and enumerates the (already-known) set. The v0.3 graceful-vs-loud-fail
  contradiction is dissolved by the phase split: **graceful = absence** (no `view_prose.yaml` → raw
  render); **loud-fail = present-but-invalid** (unknown key/view/control-id → `ValueError`);
  `controls`/`success`/`error` are simply **not authorable** until their render surfaces exist.
- **OQ-8 (v0.5, NEW — resolved) — where does hash-exempt prose live?** Planning found the SDK hashes the
  **whole `views.yaml`** (no subset hashing exists). ✅ Resolved → **standalone `view_prose.yaml`
  rendered into an untracked fragment** (the `pages.yaml`/`ai_passes.yaml` mechanism), not a `views.yaml`
  section. Zero new hashing code; see FR-PG-10/12 and plan §1.

## 5. Hand-off to SDK-home (tekizai-tekisho)

This doc specifies the **consumer-owned contract**. The generator capability is **SDK-home work** to
be ratified/implemented there. Three distinct SDK items fall out:
1. **Content-pages generation** — consume `pages.yaml` + `app/pages/*.md`, emit `app/pages.py`
   (`pages_router`, root + content routes), owned page templates, and nav in `base.html`; three-hash
   header (`schema + pages + ?`) + `--check` drift; `--pages` CLI flag + cap-dev-pipe pass-through.
   **(Shipped.)**
2. **Form-generator fix (FR-PG-5)** — reuse the existing system/provenance/timestamp omission in the
   HTMX form generator; human-readable labels. Independent of #1. **(Shipped.)**
3. **View prose in `view_codegen` (FR-PG-10/11/12, NEW)** — `view_codegen` consumes a standalone
   **`view_prose.yaml`** (strict-parse, `parse_pages` contract; loud-fail on unknown keys/views) and
   renders it into a **header-less untracked fragment** the owned view template `{% include %}`s — so
   prose is **never hashed** yet still strict-parsed at generate time (FR-PG-12). The implementation
   plan is `startd8-sdk/docs/design/view-prose/VIEW_PROSE_PLAN_v0.1.md`. **Sequenced (v0.5, by render
   surface, not just OQ-7):**
   - **3a — Phase 1 (buildable now; no substitution, no new surface):** keys `title`/`intro`/`empty`,
     rendered for the three archetypes that already emit HTML (`detail-compose`, `computed-panel`,
     `import-flow`). New module `view_prose.py` (parser) + a fragment renderer + `--view-prose` CLI flag,
     all copies of the shipped `pages` mechanism. Opportunistically removes the hardcoded-title f-strings
     and scattered empty-state literals on the lines it touches (plan §6 AC-1/AC-2). **Unblocked.**
   - **3b — Phase 2 (each gated on a NEW render surface):** (a) `controls` labels — stamp stable ids on
     the anonymous import-flow buttons, then consume the closed `validate`/`restore`/`confirm` set;
     (b) `success`/`error` (**import-flow only**) — add an HTML outcome surface, then whitelist-substitute
     the corrected closed token set (`{errors}`/`{counts}` for validate, `{imported}`/`{total}` for
     restore); (c) `export-package` `title`/`intro` — add an HTML landing surface to the archetype. The
     computed-panel's **per-signal nudge strings stay archetype-owned** (not a prose key — FR-PG-11
     exception).

   **Do NOT touch (plan §6, flagged-not-now):** the mixed `render_view_module` dispatch (AC-3), the
   `_PROSE_MODULE` baked-string (AC-4), the label-fallback split (AC-6), and test-scaffold duplication
   (AC-7) are pre-existing accidental complexity **off the prose path** — refactoring them now is scope
   creep. **Naming (AC-5):** the new view-**chrome** prose is distinct from the existing `prose_key`/
   `prose_body` entity-content prose; the standalone file + a `ViewProse` type keep them uncollided.

   Tracked in `docs/SDK_QUICK_WINS_2026-06-10.md` #7.

---

*v0.5 — Post-planning reflective update (drove by the SDK-home plan `VIEW_PROSE_PLAN_v0.1.md`,
grounded in `view_codegen/` at file:line). Two v0.4 assumptions overturned: (1) **prose moved from a
`views.yaml` `prose:` section to a standalone `view_prose.yaml`** rendered into an untracked fragment —
the whole `views.yaml` is hashed, so hash-exemption is only achievable by a separate file (zero new
hashing code; FR-PG-10/12, new OQ-8 resolved); (2) **Phase 1 narrowed to `title`/`intro`/`empty`** —
`success`/`error` are import-flow-only with no HTML surface, and `export-package` renders no HTML page,
so those + `controls` moved to Phase 2 (each gated on a new render surface). Placeholder vocabulary
corrected (success = `{imported}`/`{total}`; export has none; panel = `{score}`/`{present}`). OQ-7
resolved (controls are a closed trivial enum; sequenced not risky). Added an accidental-complexity
ledger to SDK hand-off #3 (opportunistic AC-1/AC-2; flagged-not-now AC-3..7).*
*v0.4 — View-prose hardening (pre-build review). Phased FR-PG-10's key-set; `controls:`
reserved-until-built behind OQ-7 (resolving the v0.3 graceful-vs-loud-fail contradiction); closed the
placeholder vocabulary; documented the `/completeness` per-signal-nudge exception; clarified hash-exempt
prose is still strict-parsed at generate time; split SDK hand-off #3 into 3a/3b. (Superseded in part by
v0.5: the placeholder set and the in-`views.yaml` placement were corrected.)*
*v0.3 — View prose. Added FR-PG-10 (the `views.yaml` `prose:` grammar), FR-PG-11 (apply to the four
shipped composite archetypes with acceptance copy), FR-PG-12 (prose outside the drift hash); 1 new
open question (OQ-7, control_id stability); SDK hand-off item #3 added.*
*v0.2 — Post-planning self-reflective update. 1 requirement reframed (FR-PG-5) + split to a separate
SDK contract, 1 tightened to strict-parse (FR-PG-6), 6 open questions resolved, SDK hand-off (§5) added.*

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
