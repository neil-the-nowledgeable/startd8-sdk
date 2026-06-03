# Convergent Review Prompt

**Generated:** 2026-06-03 17:27:55 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)** — initializing the Appendix A/B/C scaffold if the doc has none yet (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`). The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 10 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/semantic-compliance/SEMANTIC_COMPLIANCE_REVIEWER_PLAN.md` | 104 lines · 749 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/semantic-compliance/SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` | 246 lines · 2352 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/semantic-compliance/SEMANTIC_COMPLIANCE_REVIEWER_PLAN.md`  ·  **Size:** 104 lines · 749 words

```markdown
# Semantic Compliance Reviewer — Implementation Plan

**Version:** 0.2 (post-reflection, paired with requirements v0.2)
**Date:** 2026-06-03
**Status:** Plan — pre-implementation
**Tracks:** `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md` v0.2

---

## Design summary

The SCR is the **first producer** of the dormant `SemanticVerificationResult` (K-7) contract.
It compares generated output against the *original requirement* for selected features and routes
findings into Kaizen so the next run is more compliant. Post-run / Service-Assistant-orchestrated
first; same contract designed to be hoisted into the in-run `MicroPrimeConfig.semantic_verification_*`
hook later. Tiered (cheap triage → Haiku review → Sonnet escalation); advisory in v1.

```
SA detects completed run
   └─ triggers SCR (within escalation budget)
        1. load prime-context-seed*.json → feature→requirement map      (FR-1)
        2. read prime-postmortem-report.json → per-feature triage signals (FR-4)
        3. rank suspicion; pick escalations + bounded PASS sample        (FR-5/5a)
        4. assemble (requirement + design intent + generated files)      (FR-1/2/3)
        5. Haiku review → SemanticVerificationResult; Sonnet on fail/low-conf (FR-6/15)
        6. score + dedup vs semantic_issues                              (FR-8, OQ-5)
        7. write semantic-compliance-report.json/.md                     (FR-9)
        8. emit templated hints → kaizen-suggestions.json + cross-feature patterns (FR-10/11)
        9. SA folds results into triage artifact + SEMANTIC_REVIEW_COMPLETE event (FR-12)
```

## Module layout

| New artifact | Purpose | Maps to |
|--------------|---------|---------|
| `src/startd8/semantic_compliance/__init__.py` | Package + `SemanticComplianceReviewer` facade | all |
| `.../requirement_loader.py` | Load `prime-context-seed*.json`, feature→task map | FR-1 |
| `.../triage.py` | Suspicion ranking from post-mortem signals + PASS sample | FR-4/5/5a |
| `.../reviewer.py` | Agent invocation → `SemanticVerificationResult` (Haiku→Sonnet) | FR-6/15 |
| `.../prompts.py` | Versioned requirement-anchored review rubric | FR-7 |
| `.../scoring.py` | `semantic_compliance_score`, dedup vs semantic_issues | FR-8 |
| `.../report.py` | `semantic-compliance-report.json`/`.md` | FR-9 |
| `.../feedback.py` | Templated hints → kaizen `prompt_hints`; cross-feature patterns | FR-10/11 |
| `prime_postmortem.py` (edit) | add `requirement_semantic_gap` → `CAUSE_TO_SUGGESTION` | FR-10 |
| `service_assistant/` (edit) | trigger SCR; fold results; `SEMANTIC_REVIEW_COMPLETE` event | FR-12 |
| `micro_prime/models.py` | reuse `SemanticVerificationResult` (no change) | FR-6/13 |

## Step-by-step

1. **Requirement loader** — read `prime-context-seed*.json` (`tasks[].config.{requirements_text,
   task_description}` + `prompt_constraints`); map feature_id→task. Missing → `inconclusive`
   (`requirement_text_unavailable`). *(FR-1)*
2. **Triage** — from `prime-postmortem-report.json`: rank by `requirement_score`, `assembly_delta`,
   `semantic_error_count`/`semantic_issue_summary`, `verdict`, sibling shared `root_cause`; add a
   bounded `fake_work_stub`-adjacent PASS sample. *(FR-4/5/5a)*
3. **Input assembly** — requirement text + forward-manifest `InterfaceContract.binding_text` +
   CKG `ProjectKnowledge.{field_sets,negatives}` + generated files (`generated_files`). *(FR-1/2/3)*
4. **Reviewer** — resolve agent via `model_catalog` (`SEMANTIC_VALIDATOR`=Haiku). Single-shot
   `agenerate` → `validate_semantic_verification_json`. On `fail`/low-confidence, escalate to
   `CODE_REVIEW`=Sonnet. Multi-sample voting behind a flag. *(FR-6/15)*
5. **Rubric** — versioned prompt anchored on requirement satisfaction + honoring named
   contracts/field authorities + not inventing forbidden constructs (CKG negatives). *(FR-7)*
6. **Scoring + dedup** — `semantic_compliance_score` from verdict+confidence+issue severities;
   drop issues whose category already appears in `disk_compliance.semantic_issues`. *(FR-8, OQ-5)*
7. **Report** — `semantic-compliance-report.json` (+ `.md`): per-feature verdicts/issues/scores,
   triage+escalation decisions, requirement text reviewed. *(FR-9)*
8. **Feedback** — template hint strings from each issue's `suggested_fix` into
   `kaizen-suggestions.json` `prompt_hints`; register generic `requirement_semantic_gap`
   `{phase,hint}`; emit cross-feature semantic patterns when ≥2 features share a gap. *(FR-10/11)*
9. **SA orchestration** — SA triggers SCR within budget, folds compliance summary into
   `service-assistant-triage.json`, emits `SEMANTIC_REVIEW_COMPLETE`. *(FR-12)*
10. **OTel** — span attrs: `scr.review_count`, `scr.escalations`, `scr.cost_usd`,
    `scr.avg_confidence`, verdict distribution. *(FR-16)*

## Reuse map (don't reinvent)

| Need | Existing component |
|------|--------------------|
| Verdict contract | `SemanticVerificationResult` / `VerificationIssue` (`micro_prime/models.py`) |
| Triage signals | `FeaturePostMortem` fields in `prime-postmortem-report.json` |
| Requirement text | `prime-context-seed*.json` → `SeedTask` (`seeds/models.py`) |
| Design intent | `InterfaceContract.binding_text`; CKG `ProjectKnowledge` (`contractors/project_knowledge/`) |
| Feedback loop | `generate_kaizen_suggestions` / `kaizen-suggestions.json` / `_apply_kaizen_hints` |
| Model tiers | `Models.SEMANTIC_VALIDATOR` (Haiku), `Models.CODE_REVIEW` (Sonnet) |
| In-run home (Phase 2) | `MicroPrimeConfig.semantic_verification_{enabled,agent_spec,fn}` |
| Orchestration | `service_assistant/` (detect→trigger→fold) |

## Risks / watch-items

- **Requirement text absent** (OQ-1) — must degrade to `inconclusive`, never fabricate compliance.
- **Cheap-tier reliability** (OQ-4) — Haiku `fail` verdicts may be noisy; escalate to Sonnet before
  emitting a high-severity Kaizen hint; keep multi-sample voting available for gating-readiness.
- **Double-reporting** (OQ-5) — dedup SCR findings against `semantic_issues` categories.
- **Altitude** (OQ-9) — feature-level vs element-level verdict comparability with the Phase-2 hook.
- **Cost creep** — escalation budget + PASS-sample cap must be enforced and logged (no silent caps).

## Verification

- [ ] Every FR (1–16, 5a) has a step; every step traces to an FR.
- [ ] Requirement-unavailable → `inconclusive` (not a false PASS/FAIL).
- [ ] Tiered: Haiku-only on clear cases; Sonnet only on fail/low-confidence (cost asserted).
- [ ] run-018 replay: 6 shared-cause features → one cross-feature semantic pattern + templated hint.
- [ ] False-PASS: a `fake_work_stub`-adjacent PASS gets sampled and flagged.
- [ ] Advisory: no run blocked; schema carries verdict+confidence for future gate.
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/semantic-compliance/SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md`  ·  **Size:** 246 lines · 2352 words

```markdown
# Semantic Compliance Reviewer — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-03
**Status:** Draft
**Owner:** neil-the-nowledgable
**Related:** `docs/design/service-assistant/` (the Service Assistant orchestrates this reviewer post-run)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning) and v0.2. The planning pass mapped each requirement
> to real seams and revealed 5 material corrections; all 8 open questions are resolved or
> reduced, and 1 new wrinkle (altitude) surfaced.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Requirement text is available at review time (FR-1) | The post-mortem only uses seed tasks **when explicitly passed**; nothing reads `prime-context-seed.json` back, and there's no auto-discovery (unlike `kaizen-suggestions.json`). The seed file **is** written to the run dir, though, with `tasks[].config.{requirements_text,task_description}`. | **FR-1 sharpened.** The SCR must **load+parse `prime-context-seed*.json` itself** and map feature→seed task (by id). Requirement text is recoverable, but only via explicit seed-file loading — not from the post-mortem report. |
| The `SemanticVerificationResult` socket is purely dormant (FR-6) | It's dormant **and so is its config**: `MicroPrimeConfig` already declares `semantic_verification_enabled` / `semantic_verification_agent_spec` / `semantic_verification_fn` — unwired, at the **element** (micro_prime) level. The contract's `element_fqn` field is element-scoped. | **FR-13 sharpened + new altitude note.** The Phase-2 in-run hoist has a pre-existing home (those flags). But post-run review is **feature/file-scoped** while the contract+config are **element-scoped** — an altitude mismatch the contract must bridge (OQ-9). |
| Confidence comes "for free" from the verdict (FR-6) | The review path (`PrimeReviewAdapter._review_task`) is **single-shot**; there is **no self-consistency/voting** anywhere to reuse. Multi-sample confidence is net-new N× token cost. | **FR-6 revised.** Default to single-shot using the contract's own `confidence` field; **multi-sample voting is opt-in** (for gating-readiness), not v1 default. |
| One generic Kaizen hint per cause suffices (FR-10) | Hints flow as a **single newline-joined bullet list** (`generate_kaizen_suggestions` → `kaizen-suggestions.json` → `_apply_kaizen_hints` → `gen_context["kaizen_hints"]`), not per-phase at that layer. A static `CAUSE_TO_SUGGESTION` entry is generic; requirement-*specific* hints need per-feature emission. | **FR-10 refined.** The SCR emits **requirement-anchored hint strings** (templated from each issue's `suggested_fix`) directly into the suggestions pipeline, **plus** a generic `requirement_semantic_gap` fallback in `CAUSE_TO_SUGGESTION`. |
| Reviewer model tier is an open choice (FR-15) | `model_catalog.py` already defines `Models.SEMANTIC_VALIDATOR` (Haiku) and `Models.CODE_REVIEW` (Sonnet). | **FR-15 sharpened.** Escalation = a **model-tier escalation**: cheap Haiku review on flagged features → Sonnet re-review only on low-confidence/`fail`. Reuse `semantic_verification_agent_spec` config name. |

**Resolved open questions:**
- **OQ-1 → RESOLVED.** SCR loads `prime-context-seed*.json` from the run dir and maps feature→task by id (FR-1). Confirm presence + add a graceful "requirement text unavailable → mark `inconclusive`" path.
- **OQ-2 → RESOLVED.** Triage signals are all readable post-run from `FeaturePostMortem`: `requirement_score`, `assembly_delta`, `disk_quality_score`, `semantic_error_count`, `semantic_issue_summary`, `verdict`, `root_cause`, and `target/generated/missing_files`. No cheap-LLM pre-filter tier needed for ranking.
- **OQ-3 → REDUCED to a decision.** False-PASS sampling stays in scope: deep-review a small bounded sample of structurally-clean PASS features (FR-5a) so the run-018 trap is covered without full-run cost.
- **OQ-4 → RESOLVED.** No voting to reuse; single-shot default, opt-in multi-sample (FR-6).
- **OQ-5 → RESOLVED.** `semantic_issues` are `{category|check, severity, message, line}` dicts (`SemanticIssue` / dict form). SCR **consumes** them as triage input and only adds *requirement-intent* findings — dedup by category (FR-8).
- **OQ-6 → RESOLVED.** Emit templated per-feature hints into `kaizen-suggestions.json`'s `prompt_hints` + register a generic `requirement_semantic_gap` `{phase, hint}` entry (FR-10).
- **OQ-7 → RESOLVED.** SCR lives in a new `semantic_compliance/` package; the producer fills `SemanticVerificationResult` via `from_json`/`validate_semantic_verification_json`. It composes with `PrimeReviewAdapter` for the Phase-2 in-run path but does not require modifying it for post-run v1.
- **OQ-8 → carried (gating deferred).** Schema carries `verdict` + `confidence` so a future `STARTD8_SEMANTIC_GATE` can gate on `verdict=="fail" AND confidence>=θ`; θ tuned in Phase 2.

---

## 1. Problem Statement

The Prime Contractor pipeline can mark a feature **PASS** while the generated code does not
actually satisfy the *requirement that was provided as input*. Today's compliance signals are
**structural and shallow**:

- `FeaturePostMortem.requirement_score` is **keyword/substring matching** of the seed task
  description against the feature description + error text (`prime_postmortem.py` `_score_requirements`).
  It cannot tell whether the code *means* what the requirement asked for.
- The deterministic semantic checks (`validators/semantic_checks.py`, the 10 disk-compliance
  layers in `forward_manifest_validator.py`) catch *code smells* (stubs, dupes, fake-work,
  bad imports) — not *requirement intent*.
- The one **agent-driven** semantic contract — `SemanticVerificationResult` (Keiyaku K-7,
  `micro_prime/models.py`) — is **fully defined but never wired in.** It's a dormant socket.

**Concrete failure mode (observed, run-018):** 6 features failed with the *same* root cause
(`cross_file_contract`), yet the post-mortem emitted **zero `cross_feature_patterns`** — it saw
six isolated structural faults, not one systemic semantic problem. A deeper, requirement-aware
agent review would have recognized the shared intent violation and fed a single high-value
correction back into the next run.

We need a capability that performs **deeper, agent-driven analysis of whether generated
outputs semantically comply with the original input requirements**, and routes that analysis
back into the generation loop so the *next* run produces more compliant code — at controlled cost.

### Gap table

| Compliance dimension | Today | Gap |
|----------------------|-------|-----|
| Requirement intent vs output | keyword match (`requirement_score`) | No semantic judgment of "does this do what was asked" |
| Agent-driven semantic verdict | `SemanticVerificationResult` defined, **unwired** | No producer fills the socket |
| False-PASS detection | `check_fake_work_stub` (structural only) | Semantically-empty-but-structurally-valid PASS slips through |
| Cross-feature semantic patterns | structural root-cause grouping | Shared *intent* violations not recognized (run-018) |
| Feedback to next run | Kaizen Phase C (`CAUSE_TO_SUGGESTION`) | No `requirement_semantic_gap` cause feeding it |
| Cost control on deep review | n/a (no deep review exists) | Must not deep-review every feature every run |

---

## 2. Goals & Non-Goals (summary)

**Goal:** A **Semantic Compliance Reviewer (SCR)** — an agent-driven worker that, for selected
features, compares the *generated output* against the *original requirement* (+ design intent)
and emits a structured `SemanticVerificationResult`, scored and routed into the Kaizen feedback
loop. The **Service Assistant orchestrates it post-run**; the same reviewer contract is designed
so it can later be **hoisted into the in-run pre-merge gate** (phased).

**Decided shape (from product forks):**
- **Timing — phased.** Post-run / SA-orchestrated **first**; contract designed for later in-run gate reuse.
- **Selectivity — tiered.** A cheap deterministic triage flags suspect features; the **expensive
  agent review fires only on flagged features** (cost discipline per the cheap-model strategy).
- **Authority — advisory now, gating opt-in later.** v1 emits suggestions + triage signal only;
  a future flag can make a failing verdict gate.

**Not a goal (v1):** gating/blocking runs by default; replacing the deterministic checks;
re-generating code itself; deep-reviewing every feature.

---

## 3. Requirements

### Input assembly (output ↔ requirement comparison)

- **FR-1 — Requirement retrieval.** For a feature under review, the SCR SHALL **load and parse
  `prime-context-seed*.json` from the run dir itself** (the post-mortem does not persist or
  auto-discover it) and map the feature to its seed task by id, recovering the original
  requirement text (`tasks[].config.{requirements_text, task_description}` + any acceptance
  criteria / `prompt_constraints`). When the seed file or mapping is unavailable, the SCR SHALL
  mark the feature `inconclusive` with reason `requirement_text_unavailable` rather than guessing.

- **FR-2 — Design-intent enrichment.** The SCR SHALL attach available design-intent context to
  the review: forward-manifest `InterfaceContract.binding_text` for the task, and CKG
  `ProjectKnowledge` authorities (`field_sets`, `negatives` — "invent X, use Y") when present.

- **FR-3 — Generated-output retrieval.** The SCR SHALL load the generated code for the feature
  (the files it produced on disk) as the artifact under semantic review.

### Tiered selection (cost discipline)

- **FR-4 — Cheap triage pass.** Before any agent call, the SCR SHALL run a **deterministic
  suspicion triage** over each feature using already-computed signals — low `requirement_score`,
  positive `assembly_delta`, `fake_work_stub` / semantic_issues present, failed/PARTIAL verdict,
  shared root cause across siblings — producing a `suspicion` ranking.

- **FR-5 — Escalation budget.** The SCR SHALL deep-review (agent call) **only features above a
  configurable suspicion threshold**, bounded by a per-run escalation budget (max features and/or
  max token cost). Skipped features SHALL be recorded as `not_reviewed` with the reason, never
  silently dropped (no-silent-caps).

- **FR-5a — False-PASS sampling.** To catch structurally-clean-but-semantically-empty PASS
  features (the run-018 trap), the SCR SHALL deep-review a small, bounded **sample of PASS
  features** even when they clear the suspicion threshold — prioritizing those adjacent to
  `fake_work_stub` signals — so false-PASS is detectable without full-run review cost.

### Agent-driven semantic review

- **FR-6 — Semantic verdict production.** For each escalated feature, the SCR SHALL invoke a
  reviewing agent that returns a **`SemanticVerificationResult`** (the existing K-7 contract:
  `verdict` ∈ pass|fail|inconclusive, `confidence`, `issues[]` with category/severity/
  description/line_hint/suggested_fix, `element_fqn`). The SCR SHALL parse via the contract's
  `from_json` / `validate_semantic_verification_json` (fail-open on format, fail-closed on
  content). It is the **first producer** of this dormant contract. Review is **single-shot by
  default**, using the contract's own `confidence` field; **multi-sample self-consistency voting
  is opt-in** (gating-readiness) since no voting pattern exists to reuse and it multiplies cost.

- **FR-7 — Requirement-anchored rubric.** The review prompt SHALL anchor the agent on
  *requirement satisfaction* (does the code implement the asked-for behavior, honor the named
  contracts/field authorities, avoid inventing forbidden constructs) — distinct from generic
  code-quality. The rubric/prompt SHALL be a versioned, single-source template.

### Scoring & artifacts

- **FR-8 — Compliance score.** The SCR SHALL derive a per-feature `semantic_compliance_score`
  (from verdict + confidence + issue severities) and a run-level aggregate, distinct from and
  complementary to the structural `disk_quality_score`.

- **FR-9 — Persisted artifact.** The SCR SHALL write a structured artifact
  (`semantic-compliance-report.json` + a human `.md`) to the run output dir, holding per-feature
  verdicts, issues, scores, the triage/escalation decisions, and the requirement text reviewed.

### Feedback routing (produce better code next run)

- **FR-10 — Kaizen integration.** The SCR SHALL route confirmed semantic gaps into the existing
  Phase C feedback loop. Because hints flow as a single newline-joined bullet list
  (`generate_kaizen_suggestions` → `kaizen-suggestions.json` `prompt_hints` → `_apply_kaizen_hints`
  → `gen_context["kaizen_hints"]`), the SCR SHALL emit **requirement-anchored hint strings
  templated from each issue's `suggested_fix`** directly into that `prompt_hints` list, **and**
  register a generic `requirement_semantic_gap` → `{phase, hint}` fallback entry in
  `CAUSE_TO_SUGGESTION`. Hints are injected into the next run's spec/draft prompts.

- **FR-11 — Cross-feature semantic patterns.** When ≥2 features share a semantic gap category
  or violate the same requirement/contract, the SCR SHALL emit a **cross-feature semantic
  pattern** (the signal the structural post-mortem missed on run-018), elevated in severity.

### Orchestration & phasing

- **FR-12 — Service Assistant orchestration (post-run).** The Service Assistant SHALL, on
  detecting a completed run, trigger the SCR (subject to the escalation budget), and SHALL fold
  the SCR's results into its triage artifact + events (new `SEMANTIC_REVIEW_COMPLETE` signal).

- **FR-13 — In-run hoist contract.** The SCR's input/output contract SHALL be defined so the
  same reviewer can later be invoked **in-run pre-merge** without changing its interface — only
  its trigger and authority change. The Phase-2 in-run home is the **pre-existing but unwired
  `MicroPrimeConfig.semantic_verification_{enabled,agent_spec,fn}` hooks** (element-level); the
  SCR SHALL reuse the `semantic_verification_agent_spec` config name and the same
  `SemanticVerificationResult` output so the post-run worker and the in-run hook are the same
  code at different triggers. (In-run wiring deferred to Phase 2; contract compatibility in scope.)

### Authority & cost

- **FR-14 — Advisory by default, gating opt-in.** v1 SHALL treat verdicts as advisory (feed
  Kaizen + triage; never block). The result schema SHALL carry enough (verdict + confidence) for
  a future `STARTD8_SEMANTIC_GATE` flag to make a low-confidence-independent `fail` gate a run.

- **FR-15 — Model-tier control / tiered escalation.** The reviewing agent's model SHALL be
  resolved via `model_catalog.py` — not a hardcoded string — reusing `Models.SEMANTIC_VALIDATOR`
  (Haiku) for the cheap first review and `Models.CODE_REVIEW` (Sonnet) for escalation. The
  tiered design (FR-5) SHALL be realized as a **model-tier escalation**: cheap Haiku review on
  flagged features, escalating to Sonnet re-review only on `fail` / low-confidence verdicts.

- **FR-16 — Observability.** The SCR SHALL emit OTel spans/metrics for reviews run, escalations,
  verdict distribution, and token cost, consistent with the SDK's existing event/OTel bridge.

---

## 4. Non-Requirements

- **NR-1.** No gating/blocking of runs in v1 (advisory only; gating behind a future flag).
- **NR-2.** Does not replace the deterministic semantic checks or disk-compliance layers — it is
  an additive, agent-driven layer that *consumes* their signals for triage.
- **NR-3.** Does not regenerate or edit code — it reviews and recommends (the generation loop /
  repair pipeline acts on the Kaizen hints next run).
- **NR-4.** Does not deep-review every feature by default (tiered escalation; full-review is an
  opt-in mode).
- **NR-5.** Not a new classification taxonomy — reuses `SemanticVerificationResult` categories
  and the Kaizen `CAUSE_TO_SUGGESTION` mechanism.
- **NR-6.** In-run pre-merge gating wiring is out of scope for v1 (Phase 2); only contract
  compatibility is in scope.

---

## 5. Open Questions

> OQ-1 through OQ-8 were resolved or reduced by the planning pass — see §0 "Resolved open
> questions." Retained here condensed for traceability; one new question (OQ-9) surfaced.

- **OQ-1 → RESOLVED.** SCR loads/parses `prime-context-seed*.json` itself; `inconclusive` when unavailable.
- **OQ-2 → RESOLVED.** Post-mortem signals suffice for suspicion ranking; no cheap-LLM pre-filter needed.
- **OQ-3 → RESOLVED (decision).** Bounded PASS sampling (FR-5a), `fake_work_stub`-adjacent first.
- **OQ-4 → RESOLVED.** Single-shot default; opt-in multi-sample voting (FR-6).
- **OQ-5 → RESOLVED.** Consume `semantic_issues` as triage input; add only requirement-intent findings, dedup by category.
- **OQ-6 → RESOLVED.** Templated per-feature hints into `prompt_hints` + generic `requirement_semantic_gap` fallback (FR-10).
- **OQ-7 → RESOLVED.** New `semantic_compliance/` package; SCR is the first `SemanticVerificationResult` producer.
- **OQ-8 → CARRIED (gating deferred).** Schema carries `verdict`+`confidence` for a future `STARTD8_SEMANTIC_GATE` (gate on `fail AND confidence≥θ`); θ tuned in Phase 2.

### New open question surfaced during planning

- **OQ-9 — Review altitude (feature vs element).** Post-run review is **feature/file-scoped**,
  but `SemanticVerificationResult` + the `MicroPrimeConfig.semantic_verification_*` hooks are
  **element-scoped** (`element_fqn`). For v1 the SCR reviews at the feature level (feature name →
  `element_fqn`); does requirement compliance need element-granular review for large multi-element
  features, or is feature-level sufficient until the Phase-2 in-run (element-level) hoist? Decide
  the granularity contract so post-run and in-run produce comparable verdicts.

---

*v0.2 — Post-planning self-reflective update. 5 requirements revised (FR-1/6/10/13/15), 1 added
(FR-5a), 8 open questions resolved/reduced, 1 new (OQ-9 altitude). Architecture: a new
`semantic_compliance/` package = the first producer of the dormant `SemanticVerificationResult`
contract; Service Assistant orchestrates post-run; tiered Haiku→Sonnet escalation; advisory→Kaizen.
Ready for optional Convergent Review.*
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
