# Convergent Review Prompt

**Generated:** 2026-08-14 16:16:56 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per \`CONVERGENT_REVIEW_AGENT_GUIDE.md\`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (2 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 1 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 2 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 6 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/CRUD_LIST_EMPTY_STATE_PLAN.md` | 177 lines · 1472 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/CRUD_LIST_EMPTY_STATE_REQUIREMENTS.md` | 302 lines · 3480 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/_crp/FOCUS_LIST_EMPTY.md` | 9 lines · 44 words |

Treat the embedded documents below as the **authoritative review surface** for this
round: do **not** rewrite plan/requirements body prose (Appendix C append only —
that is what "read-only" means here). If something conflicts between plan and
requirements, call it out explicitly in suggestions and in the coverage mapping.

When the docs extend or modify an **existing** system (not greenfield), you **MAY
and SHOULD** open **named** files/symbols the docs cite (or that the plan's file
list implies) to check real APIs, reuse opportunities, and accidental-complexity
risks (parallel machinery, reinvented helpers, wrong layer). Do **not** run
open-ended repo-wide exploration unrelated to validating a concrete suggestion —
persist Appendix C first; targeted code reads are in service of better suggestions,
not a substitute for writing them.

---

## Your Task

You are a **senior architectural reviewer** with **file-edit tools** (Write/Edit/equivalent) and filesystem access to the source documents listed above (and, when needed for non-greenfield grounding, **read** access to named implementation files those docs cite). Your job is to produce **improvement suggestions** (structured, anchored, actionable) and **persist them directly into the source documents** by appending a new **Review Round** under each reviewed document's **Appendix C (Incoming)** — see **Prior Review State** below.

**First, read the existing review state** (Appendix A/B/C) in each source doc and **avoid re-proposing** what is already settled (A) or rejected (B), and **avoid near-duplicates** of untriaged items in C (dedup rules below). Every in-scope doc already contains a \`## Appendix: Iterative Review Log\` with an empty A/B/C scaffold (the generator created it) — **append your round to Appendix C**; do **not** create a second scaffold.

**Do not** triage (no ACCEPT/REJECT disposition for your own or others' suggestions — that is orchestrator-side and lands in Appendix A/B), **do not** modify or rewrite existing prose, **do not** alter Appendix A/B or **prior rounds** in Appendix C, and **do not** emit a numbered suggestion list in chat — the orchestrator reads them from the files.

Optimize for **actionable, mergeable feedback** written into the right file.

### Prior Review State — read this BEFORE writing suggestions

Each source document **is** the persistent review state. Before proposing anything, parse its \`## Appendix: Iterative Review Log\` (if present):

- **Appendix A (Applied / Accepted)** — settled improvements. **Do not re-propose** anything here.
- **Appendix B (Rejected)** — read each **rationale**. Do **not** re-propose a rejected idea unless you explicitly cite its ID and argue why the rationale no longer holds.
- **Appendix C (Incoming)** — prior rounds, some untriaged. **Do not duplicate** a near-identical suggestion; if you agree with an untriaged item, **endorse** it (see Deliverables) instead of restating it.

**Your round number** is \`R{n}\` where **n = (highest existing \`#### Review Round R{n}\` in Appendix C) + 1**, or **1** if none exist. Put it in every suggestion ID: **R{n}-S{k}** (plan) / **R{n}-F{k}** (requirements).

**Go deeper, not wider:** prior reviewers caught the obvious issues — look for what they missed (second-order effects, cross-cutting concerns, interactions between already-accepted suggestions), and spend effort on areas with **few accepted** suggestions rather than those already **substantially addressed** (2+ accepted).
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
| Max suggestions (soft cap) | 6 |
| Review areas to consider | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |
### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

# CRP-lite focus — CRUD list empty-states

Least-reviewed: this pair. Settled: reuse `onboarding.empty_states` (not `list_empty:`); Sotto untracked fragment.

Weight:
1. Filtered-empty vs true-empty (query_params trap)
2. Table suppression vs empty thead
3. Coherence with welcome checklist without double CTA
4. Drift: htmx-list stays 1-hash

**If the focus file above contains numbered asks** (e.g. `A1`/`A2`/`Ask 1`/`Ask 2` or similar), address each ask **at the top of your appended round**, before standard S/F-prefix suggestions, using this template per ask (orchestrator triages later — **no** ACCEPT/REJECT tables here, and **no** chat-only response):

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

---

### Pre-flight (before drafting suggestions)

1. **Optionally expand** the protocol guide \`<details>\` block below and skim **quality norms** (anchoring, scope, security). You are **not** executing full CRP phase/triage automation—use the guide as reference only.
2. Read the **Document Under Review** section(s) once for structure; read again while drafting suggestions.
3. Note **explicit out-of-scope** lines — do not file suggestions that only restate excluded work unless you flag a **dependency risk** (why exclusion threatens delivery).

---

### Protocol guide — optional reference (norms for good suggestions)

**Important:** Some chat clients or models collapse \`<details>\` by default. Expand if you need **deeper** CRP vocabulary; this prompt does **not** require you to run guide phases 5–7 (triage, appendix merge, final document emit).

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/CRUD_LIST_EMPTY_STATE_PLAN.md`  ·  **Size:** 177 lines · 1472 words

```markdown
# CRUD List Empty-State — Implementation Plan

**Pairs with:** `CRUD_LIST_EMPTY_STATE_REQUIREMENTS.md` (v0.2)
**Version:** 0.2 (updated to match the post-reflection requirements)
**Date:** 2026-08-14
**Backend:** startd8-python-cascade
**Status:** PLANNED — not implemented. No code changes have been made.

---

## 0. What this plan changed after the reflection pass

| v0.1 plan step | Why it changed |
|----------------|----------------|
| "Add `list_empty_manifest.py` + parser + strict validation + CLI flag" | **Deleted.** `views.yaml` is already threaded into both `render_ui` and `_renderers`; `parse_onboarding` already validates entity keys. Nothing to build (REQ OQ-1). |
| "Introduce `htmx-list-forms` 2-hash kind + register in drift" | **Deleted.** The hash-exempt fragment keeps `list.html` schema-only (REQ FR-3 / Sotto). |
| "Insert copy + CTA under the table" | **Rewritten** as suppress-table-and-render-panel (REQ FR-1). |
| — | **Added** step 4 (`filtered` ctx + no-matches state, REQ FR-5) and step 6 (rollout regen of both dogfood apps, the `--check` blast-radius risk). |

Net effect: the plan lost a module, a manifest, a CLI flag and an artifact kind, and gained one
context key and a rollout step.

## 1. Approach

One general rule, applied uniformly: every entity list template gains an `{% else %}` branch that
renders a panel; the panel's sentence comes from an untracked per-entity fragment whose content is
resolved from `onboarding.empty_states` with a deterministic fallback. The owned templates change
once, identically, and never again on a copy edit.

Precedence resolved at generate time (not in the template):

```
onboarding.empty_states[Entity]  →  "No <Title> yet. Add the first one to get started."
```

## 2. Iterations

Each step names its files, the REQ it serves, and its dependencies. The order is acyclic.

### Step 1 — Resolve the sentence (serves FR-2, FR-8) · deps: none

- `src/startd8/backend_codegen/htmx_generator.py`
  - Add a module-private `_empty_state_copy(entity, display, onboarding_spec) -> str`: returns the
    authored `empty_states` value when present, else the deterministic default built from the display
    title (`display.title or entity`, the same resolution `render_list_template` already does at
    line 502).
  - Add `render_list_empty_fragment(entity, display, onboarding_spec) -> str` returning **headerless**
    HTML — one element carrying the sentence only, mirroring `render_form_prose_fragments`
    (`htmx_generator.py:848-879`) which is the established untracked-fragment precedent.
- No parser work: consume `onboarding_manifest.parse_onboarding(forms_text, known_entities=…)`.
  It already raises on unknown entities, so no new validation is needed or wanted.

### Step 2 — Panel in the owned list template (serves FR-1, FR-3, FR-4) · deps: 1

- `htmx_generator.py::render_list_template`
  - Wrap the existing `<table>` block in `{% if items %} … {% endif %}` and add the `{% else %}` panel:
    a `<section class="empty-state">` containing the heading, the unconditional
    `{% include "<e>/_list_empty.html" ignore missing %}`, and the primary CTA anchor to
    `/ui/<e>/new`.
  - Move the existing top-of-page `New <Entity>` link (line 511) inside the `{% if items %}` branch so
    the zero-row state has exactly one create affordance (FR-4).
  - **Invariant to hold:** the include line must name only the entity path, never the copy, and must
    not be gated on whether `onboarding:` exists — that is what keeps the `htmx-list` header honest as
    a schema-only kind. Do **not** add a views-sha to `_tmpl_header` for this kind.
- `htmx_generator.py::render_ui`
  - Parse the onboarding spec once (from the `forms_text` parameter already in scope) and emit
    `app/templates/<e>/_list_empty.html` per entity, appended the same way
    `render_form_prose_fragments` output is appended (line 1452).

### Step 3 — Panel styling (serves FR-7) · deps: 2

- `htmx_generator.py::_BASE_STYLE` — add `.empty-state` rules (card surface, ink-soft sentence,
  emphasized CTA anchor) using the existing FR-FH-11 variables with literal fallbacks. `base.html`
  stays a schema-only `htmx-base` kind; no new stylesheet or static asset.
- Note: the base style currently styles `button` but has no `.button`-style anchor rule, so the CTA
  anchor needs its own rule rather than inheriting one.

### Step 4 — Filtered-empty distinction (serves FR-5) · deps: 2

- `htmx_generator.py::_entity_routes` — in `list_<e>`, for entities with an `EntityFilter`, add a
  computed `"filtered"` key to `ctx`, true iff any **declared** facet key or the search key `q` is
  present and non-empty in `request.query_params`. Entities without a filter manifest get
  `"filtered": False` (or omit it — the template must treat undefined as false) so their output is
  otherwise unchanged.
  - **Do not** derive this from `filters`/`dict(request.query_params)`: that dict carries `created`
    after a PRG redirect and would misreport a just-created-then-empty list as filtered.
- `render_list_template` — inside the `{% else %}` branch, split on `filtered`: neutral no-matches copy
  plus a clear link to `/ui/<e>` (the filter form's existing `clear` target, line 485) versus the
  onboarding sentence plus the promoted CTA.

### Step 5 — Drift parity (serves FR-6) · deps: 1, 2

- `src/startd8/backend_codegen/drift.py`
  - Update the `"htmx-list"` renderer (line 275) to pass the onboarding spec, parsed from the
    `forms_text` already available in `_renderers` — exactly the shape `_filt` uses (line 191). Add an
    `_onb(s)` helper alongside `_filt`/`_disp`.
  - No new kind registration. The fragment is headerless, so it is already outside the owned-file set
    that `--check` walks.

### Step 6 — Tests + dogfood rollout (serves every FR) · deps: 3, 4, 5

- `tests/unit/backend_codegen/` — new cases:
  1. zero-row list body contains the panel copy and no `<table>`; one-row body contains the table and
     no panel (FR-1).
  2. household-shaped fixture: the `Member` fragment string is byte-identical to the welcome
     checklist's `Member` copy (FR-2).
  3. changing an `empty_states` value changes only the fragment; every owned artifact is byte-identical
     (FR-3) — the round-trip assertion that proves Sotto.
  4. zero-row body contains exactly one `/ui/<e>/new` href (FR-4).
  5. filtered-empty renders no-matches + clear and not the onboarding sentence; `?created=1` alone does
     **not** count as filtered (FR-5) — this is the regression guard for the trap in step 4.
  6. `views.yaml` with no `onboarding:` section still emits a per-entity fragment with the default
     sentence (FR-8).
- `tests/fixtures/wireframe/` — the fixture already declares `empty_states` for `Profile` and `Note`,
  so it is the harness as-is; regenerate its expected artifacts.
- **Rollout (the high risk in the REQ risk table):** the `list.html` change is a one-time structural
  regen for every generated app. In the same pass, regenerate the wireframe fixture and
  `~/Documents/dev/household/household-o11y` (`startd8 generate backend` with its existing
  `--form-prose` / `--human-inputs` flags) and confirm `--check` exits 0 afterward. Apps pinned on
  `--check` without regenerating will report drift — this is expected and correct, and must be called
  out in the PR body.

## 3. Verification

```bash
cd ~/Documents/dev/startd8-sdk
python3 -m pytest tests/unit/backend_codegen -q

# fixture drift parity, with and without an onboarding: section
startd8 generate backend --check   # (wireframe fixture harness) -> exit 0

# lived dogfood: regen then confirm the orphan is gone
cd ~/Documents/dev/household/household-o11y
startd8 generate backend …         # existing flag set
startd8 generate backend --check   # exit 0
curl -sS http://127.0.0.1:8000/ui/member | grep -c "Add your first household member"   # 1
curl -sS http://127.0.0.1:8000/ui/member | grep -c "<table"                            # 0 while empty
# and the copy is the same string the checklist shows
curl -sS http://127.0.0.1:8000/welcome  | grep -c "Add your first household member"     # 1
```

The last two commands together are the O-2 proof: one authored string, two surfaces.

## 4. Sequencing note

WIP=1. This is the deferred half of `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` ("Patching every generated
CRUD list template in v1" — its explicit v1 non-goal), so it should land as its own change with the
onboarding archetype already on `origin/main` (PR #463, `1379392`). CRP-lite (one Appendix-C round +
A/B triage) is the S-size default per `BACKEND_ROUTING.md`; offer it before Step 1.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/CRUD_LIST_EMPTY_STATE_REQUIREMENTS.md`  ·  **Size:** 302 lines · 3480 words

```markdown
# CRUD List Empty-State — Requirements

**Project:** startd8-sdk backend_codegen (HTMX entity list pages) · **Criticality:** medium
**Version:** 0.2 (post-planning — self-reflective update)
**Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Audience:** end-user (a person who just read the welcome checklist and opened `/ui/<entity>`)
**Pairs with:** `CRUD_LIST_EMPTY_STATE_PLAN.md`
**Inherits standards:** `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` (its deferred v1 non-goal) · PC-13 (onboarding is content, not a modal) · PC-1 (audience-keyed content) · Sotto (presence-gated, hash-exempt Words seam) · `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` (`?created` flash contract) · `FORM_FIELD_LAYOUT_FR-FH-11.md` (clipboard-ledger tokens) · det-req-kit `BACKEND_ROUTING.md` UX rows (`#7 audience/presentation`, `#13 interactive-surface/rendering`)

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed this feature needed a **new authoring surface** (a `list_empty:` section) whose copy
> would be embedded in the owned list template. Reading `htmx_generator.py`, `drift.py`,
> `onboarding_manifest.py` and the two dogfood apps falsified that on three counts: the copy already
> exists and is already threaded, the table itself (not the missing copy) is the defect, and a
> filtered-empty list is a different state that v0.1 did not distinguish. Seven corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A new `views.yaml` `list_empty:` section is needed to carry the copy | `views.yaml` text is **already threaded** into `render_ui` (as `forms_text`, `assembler.py:130`) **and** into the drift renderer registry (`drift.py:126` `_renderers(forms_text=…)`), and `onboarding.empty_states` is already an entity→copy map, already strict-validated against the Prisma schema (`onboarding_manifest.py:76-85`, `onboarding_generator._validate`) | **OQ-1 resolved: no new YAML section.** FR-2 forwards `onboarding.empty_states`; zero new plumbing, zero new CLI flag, zero new hash input |
| Authored copy is *required* — an entity with no entry gets nothing | The CTA and heading are **fully determined by the schema** (`/ui/<e>/new`, the display title) — no authoring needed to fix the orphan | FR-1/FR-8: a deterministic panel renders for **every** entity, including apps with no `onboarding:` section at all. Authored copy is an *upgrade*, not a precondition |
| Add copy + a CTA **below** the empty table | With zero rows, `render_list_template` emits a `<thead>`-only `<table>` (`htmx_generator.py:504-520` — the `{% for %}` has **no `{% else %}`**). Verified live: `household-o11y/app/templates/member/list.html` renders a bare `name/role/notes` header row over an empty `<tbody>` | FR-1 **suppresses the table entirely** at zero rows and renders the panel in its place — the header-only table is pure noise, not a container to decorate |
| The list page has "no CTA" | It already has one — `<a href="/ui/{e}/new">New {entity}</a>` (`htmx_generator.py:511`). The defect is *emphasis and adjacency*, not absence | FR-4 promotes it into the panel as the primary action and forbids a **second** competing CTA in the zero-row state |
| Copy can be embedded in the owned `list.html` | `list.html` is a **schema-only 1-hash `htmx-list` kind**. Embedding views.yaml copy would make its header dishonest and force a new 2-hash kind, re-heading every generated app's list template — and every copy edit would trip `generate backend --check` | FR-3 applies **Sotto**: the copy lives in an untracked headerless fragment (`form_prose` / `view_prose` precedent), and the owned include line is **content-independent and unconditional**, so `list.html` stays schema-only and byte-stable w.r.t. views.yaml |
| Zero rows means "nothing added yet" | `items` is **post-filter** (`_list_query_lines`, `htmx_generator.py:1034-1067`). A facet/search miss also yields zero rows — showing "Add your first Member" there is a **lie**. `filters` in ctx is `dict(request.query_params)`, which is truthy after a `?created=` redirect, so it cannot be the test | **New FR-5:** `web.py` puts a deterministic `filtered` boolean in the list ctx computed from the entity's *declared* facet/search keys only; filtered-empty gets neutral "no matches" + clear, never the onboarding copy |
| Per-entity prose (`form_prose.yaml`) is a candidate home | `form_prose.yaml` is keyed to **form fields** and strict-validates targets against writable columns (`form_prose.py:101-108`) — list chrome has no valid key there. `view_prose.yaml`'s `empty:` key exists but is keyed by **composite view name** and is accepted only on a `detail-compose`; household's own `view_prose.yaml:7-10` records that the team's authored empty-state strings have **no home** for dashboard views | **OQ-1 rejects per-entity prose for v1.** A third copy home is speculative (Mottainai); deferred to Non-goals until a second consumer needs list copy that *diverges* from onboarding |

**Resolved open questions:**

- **OQ-1 → Reuse `onboarding.empty_states`; no new section, no new prose file.** Precedence is
  `onboarding.empty_states[Entity]` → deterministic schema-derived default. This is the only option
  that makes list copy and welcome-checklist copy **the same string by construction** rather than two
  strings free to drift; the other two both create a second authoring surface for one sentence.
- **OQ-2 → The panel replaces the table, it does not accompany it.** A `<thead>`-only table is cruft.
- **OQ-3 → Copy rides a hash-exempt fragment (Sotto), the skeleton stays owned.** Copy edits keep
  `generate backend --check` green; the one-time structural change to `list.html` is identical for
  every entity and every project.
- **OQ-4 → Filtered-empty is a distinct state** with its own neutral copy (FR-5).

### 0.1 Lessons-Learned Hardening (in-session; version held at 0.2 per session brief)

> Both recall surfaces were consulted with the `#7 audience/presentation` / `#13
> interactive-surface/rendering` keys. Recorded honestly:

- **Pattern-Catalog recall — empty.** `python3 -m contextcore.learning.pattern_catalog recall
  "requirement × audience/presentation" "code × audience/presentation" "code ×
  interactive-surface/rendering"` → `(none — browse fallback)`. Fell through to the markdown catalog
  as the adapter instructs.
- **Lesson recall — no applicable hit.** `contextcore lesson recall --project lessons-craft
  --task-type requirement --text "empty state list page CTA generated template copy reuse" --tag
  "audience/presentation" --top 6` returned six 0.70-tier lessons from unrelated domains
  (frontend testing, Supabase migration pipelines, card surfaces). None bear on this draft; nothing
  applied, nothing recorded as an application.
- **[PC-13 — Onboarding Is Content, Not a Modal]** (browse fallback) — forced the check "is this
  guidance page content or overlay chrome?" → the empty-state is an **in-flow content panel** in the
  list's own `{% block content %}`, no dialog role, no focus trap, no tour library (FR-1, NR-6).
- **[PC-1 — Audience-Keyed Content]** (browse fallback) — forced "is the copy resolved by graceful
  degradation, or re-authored per surface?" → the precedence chain in FR-2 is exactly PC-1's
  `(specific)→(base)` degrade, and it reuses the *existing* authored config rather than adding an
  N+1th one.
- **[Phantom-reference audit]** — every symbol this REQ names was grepped in the owning module before
  it was written; see §Reference audit. One phantom was caught and dropped: there is no
  `list_prose.yaml` and no entity-keyed `empty` key anywhere in the tree.

### 0.2 Design-Principle Hardening (in-session; version held at 0.2 per session brief)

> Filtered `PRINCIPLE-INDEX.md` §2 on the same two keys. Four principles fired; each changed the draft:

- **[Sotto]** (`code × audience/presentation` — the index's direct key match) — "does authored content
  ride a presence-gated, hash-exempt seam, byte-identical when absent?" → **rewrote FR-3.** The
  copy moved out of the owned template into an untracked headerless fragment, and the include line was
  made unconditional and content-independent so `list.html` never gains a views.yaml dependency. This
  deleted the proposed `htmx-list-forms` 2-hash artifact kind entirely.
- **[Mottainai]** — "does a later stage re-derive what an earlier stage already produced?" → **killed
  the `list_empty:` section (OQ-1).** The welcome checklist already produced entity→copy; the list page
  forwards that artifact instead of re-requesting the same sentence from the author.
- **[Hitsuzen]** (derive the determinable) — "is authoring being asked for something the inputs already
  fix?" → **added the deterministic default (FR-8) and moved the CTA out of the copy seam**
  (FR-4): href, label and heading are derived from the schema + display title, so the panel is
  correct with zero authoring. Also made `filtered` a computed boolean rather than an authored flag.
- **[Accidental-Complexity]** — "is a layer being added to compensate for a defect one general rule
  dissolves?" → **collapsed the design to one rule**: *every* entity list gets the same panel skeleton
  with a precedence-resolved sentence. No per-entity allowlist, no opt-in flag, no
  `enable_empty_states:` toggle. Non-goal NR-7 forbids reintroducing one.
- **[Genchi Genbutsu]** — grounded every claim against the tree, not the docs: the missing `{% else %}`
  was read in `htmx_generator.py`, the orphan was confirmed in the household app's *generated*
  `member/list.html`, and the drift threading was confirmed at `drift.py:275`.

### Reference audit (phantom-reference check, §0.1)

Every symbol this REQ names, grepped in its owning module before being written:

| Named | Exists? | Where |
|-------|---------|-------|
| `render_list_template` (no `{% else %}` branch) | yes | `src/startd8/backend_codegen/htmx_generator.py:490-520` |
| `render_ui(… forms_text …)` receives `views.yaml` | yes | `htmx_generator.py:1371-1400`; caller `assembler.py:130` |
| `_renderers(forms_text=…)` → `"htmx-list"` | yes | `drift.py:126`, `drift.py:275` |
| `parse_onboarding` / `empty_states` / `empty_state_map` | yes | `onboarding_manifest.py:37,43,76-85` |
| `_list_query_lines` (post-filter `items`) | yes | `htmx_generator.py:1034-1067` |
| list ctx `filters = dict(request.query_params)` | yes | `htmx_generator.py:1122-1123` |
| headerless-fragment precedent (`render_form_prose_fragments`) | yes | `htmx_generator.py:848-879` |
| unconditional tolerant include precedent (`_nav.html`) | yes | `htmx_generator.py:338` |
| `_BASE_STYLE` FR-FH-11 tokens | yes | `htmx_generator.py:165-305` |
| household `empty_states` for Member/Chore/Bill/Medication | yes | `household-o11y/prisma/views.yaml` |
| live orphan (header-only table) | yes | `household-o11y/app/templates/member/list.html` |
| `list_prose.yaml` / entity-keyed `empty:` key | **no** | phantom — dropped in §0.1 |

## Overview

When a cascade app's welcome checklist says "Add your first household member" and the user follows it
to `/ui/member`, they land on a page that renders a table header over nothing — no orientation, no
emphasized action. This adds a **generated list empty-state**: at zero rows the entity list renders a
content panel (heading, one sentence, primary create CTA) instead of an empty table. The sentence is
forwarded from the `onboarding.empty_states` the app already authored, falling back to a deterministic
schema-derived default, so the list page and the welcome checklist read as one voice without a second
authoring surface. Deterministic, `$0`, and correct for apps that declare no onboarding at all.
Deliberately later: FK picker widgets, welcome-page redesign, confirm-walk, and per-view dashboard
empty states.

Dogfood targets: `tests/fixtures/wireframe/prisma/views.yaml` (harness — already declares `empty_states`
for `Profile` and `Note`) and `~/Documents/dev/household/household-o11y` (lived — already declares all
four, and its `onboarding.continue_href` points at `/ui/member`, the orphaned page).

## Objectives

- O-1: A user who follows the welcome checklist to a zero-row list page finds orientation and one
  obvious next action — never a bare table header.
- O-2: List copy and welcome-checklist copy are the same authored string **by construction** (one
  authoring surface, zero drift potential).
- O-3: Zero new YAML sections, zero new CLI flags, zero new artifact kinds — `$0` and inert-safe.
- O-4: Editing empty-state copy never trips `generate backend --check`.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | The one-time `list.html` structural change re-renders every generated app's list templates, so any app pinned on `--check` reports drift until it regenerates | Change is identical and content-independent for every entity; call it out in the plan's rollout step and regenerate both dogfood apps in the same pass | high |
| quality | Showing "Add your first X" on a filtered-empty list is a factual lie to the user | FR-5 computes `filtered` from declared facet/search keys only (never from raw query params, which carry `created`) | high |
| quality | Scope creep into FK pickers / welcome redesign / dashboard empty states | Explicit non-goals NR-1..NR-5; a third copy home is NR-4 | medium |
| security | The panel echoes author-supplied copy into HTML | Copy is escaped exactly as the onboarding checklist escapes it; no request data enters the fragment | low |
| cost | A second copy home would double the surface for one sentence | Mottainai forward (OQ-1); revisit only on a real diverging consumer | medium |

## Profile

Declared profile: **internal**

## Functional requirements

> Code-comment labels use the `FR-LE-n` family (FR-1 ⇒ `FR-LE-1`), matching the in-tree
> `FR-CA` / `FR-DM` / `FR-FS` / `FR-FH` precedent; the doc IDs stay plain so the det-req extractor
> parses them.

- **FR-1 — Empty-state panel replaces the header-only table.** When an entity list renders zero
  items, `list.html` emits an in-flow empty-state panel (heading, copy slot, primary CTA) and
  suppresses the `<table>` entirely instead of rendering a `<thead>`-only shell. Touches: htmx-list, htmx_generator.py. Verify: given the wireframe fixture with an empty `Profile` table,
  GET `/ui/profile` returns 200 whose body contains the panel copy and contains **no** `<table>`
  element; with one row it contains the table and no panel. Serves: O-1
- **FR-2 — Copy forwarded from `onboarding.empty_states`, no new section.** The panel sentence
  resolves by precedence `onboarding.empty_states[Entity]` → deterministic default (FR-8), read
  from the `views.yaml` text already threaded to `render_ui`/`_renderers`. No new `views.yaml` section,
  no new prose file, no new CLI flag. Touches: onboarding.empty_states, htmx-list, htmx_generator.py. Verify: given household's
  `views.yaml`, the generated `member/_list_empty.html` contains exactly the string
  `Add your first household member to get started.` — byte-identical to the sentence the welcome
  checklist renders for `Member`. Serves: O-2
- **FR-3 — Copy rides a hash-exempt Words seam; the skeleton stays owned (Sotto).** The sentence is
  written to an untracked, **headerless** fragment `app/templates/<e>/_list_empty.html`, emitted for
  every entity and `{% include %}`d by the owned `list.html` with a **content-independent,
  unconditional** include line (the `base.html` `_nav.html` precedent) — so `list.html` remains the
  schema-only `htmx-list` kind with no views.yaml dependency and no new artifact kind. Touches: htmx-list, <e>/_list_empty.html, htmx_generator.py. Verify: editing an
  `empty_states` value and regenerating rewrites only `app/templates/<e>/_list_empty.html` — every
  owned file is byte-identical and `startd8 generate backend --check` exits 0. Serves: O-4
- **FR-4 — Primary create CTA lives in the panel, and is not duplicated.** The panel renders the
  create action as the emphasized primary control pointing at `/ui/<e>/new`, deriving its href and
  label from the contract (not from the copy seam); in the zero-row state the plain top-of-page
  `New <Entity>` link is not additionally rendered, so there is exactly one create affordance.
  Touches: htmx-list, /ui/<e>/new. Verify: GET a zero-row list page body contains
  exactly one occurrence of `href="/ui/<e>/new"`; a non-empty list page still contains the top link.
  Serves: O-1
- **FR-5 — Filtered-empty is a distinct state.** For entities declaring `filters:`, the list
  handler puts a `filtered` boolean in the template context, computed **only** from that entity's
  declared facet/search keys being present and non-empty (never from raw query params, which carry
  `created`); when `filtered` is true the panel renders neutral no-matches copy plus a clear-filters
  link and **suppresses** the onboarding sentence and the create CTA promotion. Touches: fastapi-web, htmx-list, filters, htmx_generator.py. Verify: on a filtered
  entity with zero stored rows, GET `/ui/<e>` shows the onboarding sentence; GET `/ui/<e>?<facet>=zzz`
  with rows stored shows the no-matches copy and a clear link, and does **not** show the onboarding
  sentence. Serves: O-1
- **FR-6 — Drift parity.** The `htmx-list` drift renderer re-renders with the **same** `views.yaml`
  text the generate path used (the `_filt`/`_disp` precedent at `drift.py:275`), and the headerless
  fragment is skipped by `--check` as a non-owned file. Touches: htmx-list, drift.py. Verify: `startd8 generate backend --check` exits 0 on the wireframe
  fixture and on regenerated household-o11y, both with and without an `onboarding:` section. Serves: O-3
- **FR-7 — Panel styling reuses the clipboard-ledger tokens.** Panel presentation is added to the
  existing owned `htmx-base` style block using the established FR-FH-11 CSS variables with literal
  fallbacks, so an unpolished app still renders a coherent panel and `startd8 polish` can override it.
  No new stylesheet, no new static asset. Touches: htmx-base, htmx_generator.py. Verify: the
  generated `base.html` contains the empty-state panel rules and every color reads through a
  `var(--…, <literal>)` fallback; `htmx-base` remains a schema-only kind. Serves: O-1
- **FR-8 — Deterministic default; inert-safe without onboarding.** With no `onboarding:` section,
  or an entity absent from `empty_states`, the fragment carries a schema-derived default sentence
  (built from the entity's display title) and the panel still renders with its CTA — the feature never
  requires authoring and never errors on an unlisted entity. Touches: <e>/_list_empty.html, htmx_generator.py. Verify: generating a project whose `views.yaml` has no
  `onboarding:` key emits a `_list_empty.html` per entity with the default sentence, and
  `generate backend --check` exits 0. Serves: O-3

## Non-goals

- **NR-1** Welcome-page / onboarding-checklist redesign — `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` owns
  that surface; this REQ only *consumes* its `empty_states` map.
- **NR-2** FK picker widgets (pilot P1-2 stays a later enhancement; raw ID text inputs are unchanged).
- **NR-3** The multi-step `confirm-walk:` archetype.
- **NR-4** A third copy home for list chrome (`list_prose.yaml`, an entity-keyed `view_prose` key, or a
  `form_prose` extension). Deferred until a consumer needs list copy that *diverges* from onboarding.
- **NR-5** Empty states for composite views / dashboards (`view_prose`'s `empty:` on non-`detail-compose`
  archetypes stays the documented §2.3 generator gap) and for the pages/admin surfaces.
- **NR-6** Any modal, overlay, dialog role, focus trap, or tour library (PC-13).
- **NR-7** An opt-in/opt-out toggle or per-entity allowlist for the panel — one general rule, applied
  uniformly (Accidental-Complexity).
- **NR-8** Changing the `?created` flash contract, the delete row-flash contract, or list pagination.

## Owned fields

Only humans enter: `onboarding.empty_states.<Entity>` (the sentence) — already an owned field of
`ONBOARDING_ARCHETYPE_REQUIREMENTS.md`, forwarded here, not re-owned. The generator owns the panel
skeleton, the CTA href/label, the heading, the default sentence, and the no-matches copy.


## Contract projection

- **Backend:** `startd8-python-cascade`
- **Vocabulary home (cite):** `src/startd8/backend_codegen/htmx_generator.py` module docstring +
  `docs/design/python-contract-codegen/PYTHON_CONTRACT_CODEGEN_REQUIREMENTS.md` (artifact kinds and
  the owned/untracked split); onboarding grammar in `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` FR-2.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| htmx-list | template | structure | `<e>/list.html`; gains the `{% else %}` panel + unconditional include; stays schema-only |
| <e>/_list_empty.html | fragment | words | Untracked, headerless, hash-exempt (Sotto); overwritten every regen |
| htmx-base | template | structure | `base.html`; panel CSS in `_BASE_STYLE`, var-with-fallback |
| fastapi-web | route | structure | `list_<e>` gains the computed `filtered` ctx key (FR-5) |
| onboarding.empty_states | manifest-section | words | **Consumed, not defined** — owned by the onboarding archetype |
| filters | manifest-section | structure | Read for declared facet/search keys only |
| /ui/<e>/new | route | structure | The panel's primary CTA target; already exists |
| htmx_generator.py | module | structure | `render_list_template` / `render_ui` / `_BASE_STYLE` |
| drift.py | module | structure | The `htmx-list` renderer registry entry |

---

## Appendix A — Accepted (with where merged)

## Appendix B — Rejected (with rationale)

- **A new `views.yaml` `list_empty:` section** — rejected (Mottainai / OQ-1). `onboarding.empty_states`
  already carries entity→copy, is already schema-validated, and its file is already threaded into both
  the generate and drift paths. A second section would let list copy and welcome copy drift apart —
  the exact single-source failure this corpus keeps filing.
- **Per-entity list prose (`form_prose.yaml` extension or `list_prose.yaml`)** — rejected for v1 (NR-4).
  `form_prose` is field-keyed and strict-validates against writable columns; `view_prose`'s `empty:` is
  view-name-keyed and archetype-gated. Adding a third copy home for one sentence is speculative.
- **A 2-hash `htmx-list-forms` artifact kind** — rejected (Sotto, §0.2). The hash-exempt fragment plus a
  content-independent unconditional include achieves the same coherence without re-heading every
  generated app's list templates or making copy edits trip `--check`.
- **Keeping the header-only table and adding copy below it** — rejected (OQ-2). A `<thead>`-only table
  is noise; the panel replaces it.
- **Gating the panel on a per-entity opt-in flag** — rejected (NR-7, Accidental-Complexity).

## Appendix C — Incoming review rounds

*v0.2 — Post-planning self-reflective update. 7 assumptions corrected, 1 requirement added (FR-5),
1 mechanism deleted (the `list_empty:` section and its 2-hash kind), 4 open questions resolved.
In-session §0.1/§0.2 hardening applied (2 patterns via browse fallback, 5 principles); version held at
0.2 per session brief. Not yet CRP-reviewed — CRP-lite (one Appendix-C round) is the S-size default.*

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
- [ ] Appended a \`#### Review Round R{n}\` block under **Appendix C** of each source file in scope (the A/B/C scaffold is generator-created — appended to it, did not recreate it).
- [ ] Round block contains: executive summary (≤10 bullets) + numbered suggestions (**R{n}-S\*** / **R{n}-F\***); optional adversarial subsection; optional Endorsements & Disagreements block.
- [ ] Did not modify existing prose, populated Appendix A/B, or prior rounds in C.
- [ ] Appended `## Requirements Coverage Matrix — R{n}` section to the end of the **plan** file (after your round block).
- [ ] Chat reply is a **short** (1–3 line) write-confirmation listing file paths and suggestion counts — **not** the suggestion content.

**Stop after persisting** — do not triage, do not emit merged documents in chat or in the files, do not modify existing prose, populated Appendix A/B, or prior rounds in Appendix C (the A/B/C scaffold is generator-created — do not add another).
