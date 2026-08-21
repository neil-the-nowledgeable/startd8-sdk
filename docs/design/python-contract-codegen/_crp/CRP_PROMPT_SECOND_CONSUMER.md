# Convergent Review Prompt

**Generated:** 2026-08-14 16:16:57 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/ONBOARDING_SECOND_CONSUMER_PLAN.md` | 162 lines · 1557 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md` | 290 lines · 3150 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/_crp/FOCUS_SECOND_CONSUMER.md` | 9 lines · 55 words |

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

# CRP-lite focus — onboarding second consumer

Least-reviewed: this pair. Settled: navig8 selected; attorney/benchmark portal retrofit rejected (Appendix B).

Weight:
1. FR-8 household form_prose/human_inputs pre-flight — is the gate right?
2. Baseline-green bracket (two --check runs) enough attribution?
3. Scope creep into pages.yaml / redirect_root_if_empty on navig8
4. Pilot note falsifiability if verdict is negative

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/ONBOARDING_SECOND_CONSUMER_PLAN.md`  ·  **Size:** 162 lines · 1557 words

```markdown
# `onboarding:` Second Cascade Consumer — Plan

**Pairs with:** [`ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md`](./ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md) v0.2 · **Date:** 2026-08-14
**Selected consumer:** **navig8** (`~/Documents/dev/navig8`) · **Fallback:** strtd8-v2-cascade
**Status:** planned — not executed. No step below has been run as a write.

---

## Why this plan is bracketed rather than linear

navig8's `app/` is **one SDK generation behind** — measured, not assumed. All 12 drifted artifacts read
`tampered`, but the cause is staleness, not hand-editing: `app/web.py` contains **0** occurrences of
`_form_errors` where household's contains **15**, and the entity `form.html` templates predate the
FR-FH-11 layout. So navig8's baseline drift *is* PR #463's shipped surface — the very change set that
made `onboarding:` possible. Regenerating navig8 pulls it forward rather than fighting local edits,
which is what makes it a low-risk pilot; but it also means a single regeneration would fuse the
archetype delta into a 12-file catch-up. Hence S3 and S5: two `--check` transcripts around the
declaration, so the onboarding delta is attributable (FR-3, O-2).

## The recipe (FR-3) — navig8's verified flag set

Derived from the census runs on 2026-08-14. navig8 has **no** `pages.yaml`, `form_prose.yaml`,
`display.yaml`, `completeness.yaml`, or `ai_passes.yaml`, and **does** ship the nav layer
(`app/nav.py`, `app/index.py` exist) — so unlike household's recipe there is **no `--no-nav`**.

```bash
SCHEMA=prisma/schema.prisma
VIEWS=prisma/views.yaml
HUMAN_INPUTS=prisma/human_inputs.yaml
BACKEND_FLAGS="--schema $SCHEMA --views $VIEWS --human-inputs $HUMAN_INPUTS"

startd8 generate backend $BACKEND_FLAGS --check    # READ-ONLY
startd8 generate backend $BACKEND_FLAGS --out .    # WRITES
```

Omitting `--human-inputs` inflates the count from 12 to 13 and relabels files `stale` instead of
`tampered` — proof that "drifted" is meaningless without the recorded flag set, which is why FR-3
demands the recipe before the number.

**Baseline RESIDUAL (pre-declaration, measured 2026-08-14 — 12 artifacts):**

`app/main.py` · `app/nav.py` · `app/web.py` · `app/templates/base.html` ·
`app/templates/{citation,decisiontree,landmineentry,landmineregister,perspective,screeninglink,sequenceconfig,treenode}/form.html`

Target after S3: **0**. Unlike household's residual, none of these is expected to survive
regeneration — if any does, it is a genuine hand-edit and S3 stops for review.

## Preconditions (abort gates)

| # | Gate | Check | If it fails |
|---|------|-------|-------------|
| G1 | Prior consumer re-verified (FR-8) | `cd ~/Documents/dev/household/household-o11y && make check` | Currently **FAILS**: `form_prose.yaml: entry 'Medication' references unknown form field 'dose'` (reproduced on `/opt/homebrew/bin/startd8` and the SDK venv; `Medication.dose` exists on the schema and is declared `authored_by: human`, so `_writable_fields` strips it from the form). File a dated Closure-Ledger gate and cite it in S8 — do **not** fix it here, and do **not** write a `PORTABLE` verdict while it is open |
| G2 | SDK on `origin/main`, clean tree | `git -C ~/Documents/dev/startd8-sdk status --short && git log -1` | Rebase before starting; a pilot run against a dirty SDK proves nothing |
| G3 | Which `startd8` | `which startd8; ls ~/Documents/dev/startd8-sdk/.venv/bin/startd8` | Two binaries exist (`/opt/homebrew/bin/startd8` + the SDK venv). Pin **one** for every transcript and record which — mixing them silently changes what "green" means |
| G4 | navig8 tree clean + backed up | `git -C ~/Documents/dev/navig8 status --short` | S3 overwrites 12 files; commit or stash first so the catch-up is reviewable as its own diff |

## Steps

| # | Action | File(s) / command | FR | Done |
|---|--------|-------------------|-----|------|
| S1 | Re-run the census; confirm the six rows and their drift numbers still reproduce | `generate backend … --check` per consumer (REQ § Candidate census) | FR-1 | ☐ |
| S2 | Confirm the FR-2 collision gate for navig8 — all 5 `human_inputs.yaml` targets are pipeline/attorney-gate-owned, none user-typed on the create path | `navig8/prisma/human_inputs.yaml` × chosen `empty_states` entities | FR-2 | ☐ |
| S3 | **Baseline catch-up.** Run the recipe as a write; re-`--check` to **0**; commit the 12-file catch-up **alone**, no `onboarding:` yet | `navig8/app/**` | FR-3 | ☐ |
| S4 | Declare `onboarding:` in navig8's `views.yaml` using archetype FR-1/FR-2 keys only (draft below) | `navig8/prisma/views.yaml` | FR-4 | ☐ |
| S5 | Regenerate; capture the second `--check`. Added drift must be exactly the three onboarding kinds; confirm `app/main.py` gained the `onboarding_routers` try/except mount (absent today) | `navig8/app/onboarding/*`, `app/templates/onboarding/*`, `app/main.py` | FR-3, FR-5 | ☐ |
| S6 | Assert no SDK change was needed | `git -C ~/Documents/dev/startd8-sdk diff --stat src/startd8/backend_codegen/` → empty | FR-4 | ☐ |
| S7 | Runtime smoke on an empty DB; then seed one row and re-check the checklist. Fold in the navig8 doc-drift repair found while grounding (`CLAUDE.md` claims no `app/`; `docs/ASSEMBLY_INPUTS.yaml` marks `views: absent` — both false) | `run.sh` / `uvicorn app.main:app`; `navig8/CLAUDE.md`, `navig8/docs/ASSEMBLY_INPUTS.yaml` | FR-6 | ☐ |
| S8 | Write `_PILOT_2026-08-NN_onboarding-navig8.md` with both transcripts and one of `PORTABLE` / `PORTABLE-WITH-FRICTION` / `NOT-PORTABLE`; cite the G1 ledger gate | new pilot note beside this plan | FR-7, FR-8 | ☐ |
| S9 | Propagate (CL-21): update the archetype REQ's dogfood line + `_PILOT_…household.md` companions to name the third surface, and record the verdict | `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` | FR-7 | ☐ |

## S4 — draft `onboarding:` block for navig8 (prose is human-owned; this is a starting point)

Uses only archetype FR-1/FR-2 keys. `redirect_root_if_empty` is deliberately **absent** — navig8 has no
`pages.yaml` owning `/`, and adding one to exercise an optional flag is a Non-goal.

```yaml
onboarding:
  route: /welcome
  title: Getting oriented
  nav_label: Welcome
  lead: >
    navig8 walks you through a legal situation with fixed if/then questions — no AI writes
    anything you read here. Trees ship as "candidate — not yet attorney-validated" until a
    licensed attorney signs off; each tree shows its own status.
  continue_href: /ui/decisiontree
  tips:
    - Start with a Decision Tree — nodes, perspectives and citations all hang off one tree
    - A node marked referral_trigger is a hand-off point, not advice
    - Landmine registers are catalogued separately and linked to nodes by screening
  empty_states:
    DecisionTree: Create a decision tree for one area of law to get started.
    TreeNode: Add the questions and info nodes that make up the tree.
    LandmineRegister: Start a register if you are cataloguing formation failure modes.
```

**Copy review before S7** (trust boundary, REQ § Risks): tips must stay navigational. No tip may state,
paraphrase, or reassure about a `validationStatus` — that string is attorney-gate-owned and is rendered
verbatim by the app. Reviewed against navig8's UPL invariant (`nodeType=referral_trigger` requires
`uplClass=must_not_cross`).

## FR-6 smoke (S7)

```bash
cd ~/Documents/dev/navig8 && ./run.sh   # or: uvicorn app.main:app
BASE=http://127.0.0.1:8000

curl -sS -o /dev/null -w "welcome %{http_code}\n" $BASE/welcome              # expect 200
curl -sS $BASE/welcome | grep -c "Create a decision tree"                     # expect >=1 on empty DB
curl -sS $BASE/welcome | grep -ci 'role="dialog"'                             # expect 0 (PC-13: content, not modal)
curl -sS $BASE/welcome | grep -o 'onboarding_tips_dismissed'                  # storage_key present
# then create one DecisionTree via /ui/decisiontree and re-fetch:
curl -sS $BASE/welcome | grep -c "Create a decision tree"                     # expect 0; other items remain
```

## Decision rule if navig8 fails

Apply in order; do not improvise a new candidate mid-pilot.

1. **S3 leaves residual drift** (a file survives regeneration ⇒ a real hand-edit): keep navig8, document
   the residual in the recipe exactly as household's Makefile does, and proceed. This is friction, not
   failure.
2. **S6 is non-empty** (the SDK had to change): stop. Verdict is `NOT-PORTABLE`; the archetype's
   portability status is downgraded and the required SDK change becomes its own REQ. Do **not** switch
   consumers to find a greener one — that is the survivorship error this REQ exists to avoid.
3. **navig8 is structurally unusable** (e.g. its schema cannot support a meaningful checklist): fall
   back to **strtd8-v2-cascade** (16 entities, 84 drifted, no hand-built onboarding) and re-run from S1.
   Its higher drift makes S3 the dominant cost; budget for it.
4. **Never** fall back to the benchmark portal or the attorney portal — both are Non-goals.

## Deliberately not in this plan

Executing the dogfood (this pass is spec-only), fixing the household `form_prose` regression, any edit
under `src/startd8/backend_codegen/`, FK pickers, per-list CRUD empty-states, `confirm-walk:`, Welcome
Mat / Concierge, and any git commit.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/ONBOARDING_SECOND_CONSUMER_REQUIREMENTS.md`  ·  **Size:** 290 lines · 3150 words

```markdown
# `onboarding:` Second Cascade Consumer — Portability Proof (Requirements)

**Project:** startd8-sdk backend_codegen · **Criticality:** medium
**Version:** 0.2 · **Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Audience:** operator (SDK maintainers running the dogfood gate) · end-user (first-run user of the selected app)
**Trust boundary:** onboarding copy is product prose shown to end users; in a UPL-sensitive consumer the tips stay orientation, never legal advice, and never restate an attorney-gate-owned validationStatus
**Data classification:** internal (pilot evidence); the selected app's own classification governs its content.
**Pairs with:** ONBOARDING_SECOND_CONSUMER_PLAN.md
**Inherits standards:** [`ONBOARDING_ARCHETYPE_REQUIREMENTS.md`](./ONBOARDING_ARCHETYPE_REQUIREMENTS.md)
FR-1..6 (**cite, do not re-spec**) · PC-13 (onboarding is content, not a modal) ·
det-req-kit [`BACKEND_ROUTING.md`](../../../../dev-os/det-req-kit/BACKEND_ROUTING.md) ·
dev-os propagation gate (CL-21: authored ≠ propagated) · `/survivorship-audit` (assume the green is lying)

**Status:** SPECIFIED (v0.2) — not implemented. This REQ selects a consumer and defines the dogfood
gate; the dogfood itself is the PLAN's execution, deliberately not run in this pass.
Plan: [`ONBOARDING_SECOND_CONSUMER_PLAN.md`](./ONBOARDING_SECOND_CONSUMER_PLAN.md).
Prior consumers: wireframe fixture harness (`tests/fixtures/wireframe/prisma/views.yaml`) and the
household-o11y lived demo ([`_PILOT_2026-08-14_onboarding-household.md`](./_PILOT_2026-08-14_onboarding-household.md)).

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed this was a small selection-and-declare errand: pick the best-looking second product
> app, paste an `onboarding:` block, regenerate, done. The planning pass — a whole-tree census plus a
> live `generate backend --check` against every candidate — falsified that at three levels. Every
> non-pilot cascade consumer is **materially drifted** from SDK `main`, so the onboarding delta cannot
> be isolated without a baseline gate first. The most attractive candidate on paper already ships a
> **hand-built onboarding surface**, i.e. the exact shape that made the attorney portal a bad first
> dogfood. And the archetype's existing portability claim rests on one lived consumer whose **recorded
> regeneration recipe fails today**. v0.2 therefore re-centres on the *gate* — baseline-green before
> delta, an explicit disqualification rule, and a recorded negative-capable verdict — and demotes
> "declare the YAML" to one step among eight.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| Declaring `onboarding:` on a third app is a one-line delta | Every candidate is drifted from SDK main: navig8 **12** artifacts, strtd8-v2-cascade **84**, benchmark portal **97** (measured 2026-08-14 via `generate backend … --check`) | New **FR-3**: baseline-green is a *precondition*; the pilot is bracketed by two `--check` runs so the onboarding delta is attributable |
| The benchmark reviewer portal is the natural second consumer (13 entities, `pages.yaml` owns `/`, real reviewers) | It already has hand-built role-aware onboarding — `app/reviewer_intro.py` (48 lines) feeding a `/start` page — plus 97-artifact drift and a live embargoed deployment | **Rejected** and named in Non-goals; retrofitting it repeats the attorney-portal mistake the archetype explicitly avoided |
| "Two proven consumers" means the regeneration path is green today | Consumer #1's recorded recipe **fails**: household `make check` backend leg errors `form_prose.yaml: entry 'Medication' references unknown form field 'dose'` — reproduced on both the PATH binary and the SDK venv | New **FR-8**: prior-consumer re-verification is a blocking pre-flight; the portability claim may not advance on a lying green |
| The transferable asset is the `onboarding:` YAML block | The household pilot's real transferable asset is its **Makefile** — the exact verified flag set plus a documented RESIDUAL drift set. navig8, strtd8-v2-cascade and the portal have **no recorded recipe at all** | FR-3 requires *producing* the recipe; without it "regenerates green" is unfalsifiable |
| The onboarding block is self-contained | FR-4's checklist links to `/ui/<entity>` create forms, and `_writable_fields` (`htmx_generator.py:1407`) strips `human_inputs.yaml`-owned fields from those forms — so an owned field a user must type makes the first-run path dead-end. This is the mechanism behind the household `dose` failure | New **FR-2**: an owned-field × first-run-typed-field collision **disqualifies** a candidate. navig8 passes (its 5 owned fields are pipeline/attorney-gate-owned, never user-typed) |
| `redirect_root_if_empty` is exercisable anywhere | FR-2 of the archetype gates it on a `pages.yaml` page owning `/`; navig8 has **no `pages.yaml`** | Scoped out for this pilot (Non-goals) rather than bolting a pages layer onto the consumer to satisfy an optional flag |
| navig8's own docs describe its state | `navig8/CLAUDE.md` says "no `app/` generated yet" and `docs/ASSEMBLY_INPUTS.yaml` marks `views: absent` — both false; `app/` exists with 40 CRUD routes and `views.yaml` is present | Doc-drift repair folded into the PLAN (S7) as pilot fallout, not a separate loop |

### 0.1 Lessons / Pattern hardening (Phase 4.5 — honest)

Keyed lookup was **run, not skipped**: `python -m contextcore.learning.pattern_catalog recall
"requirement × single-source/no-drift" "requirement × lifecycle/bootstrap"
"code × context-arrival/data-wiring"` → **`(none — browse fallback)`**. No promoted pattern keys to
this draft's decision-classes, so no PC-ID is cited here. Claiming one would be the dormant-path
inflation the catalog exists to prevent. Fell through to the domain browse; the nearest prior art is
the household pilot note itself, which is cited directly rather than laundered into a pattern claim.

**Nomination (not a citation):** if this pilot's bracketed-`--check` gate recurs on a third adoption,
it is a promotion candidate under `single-source/no-drift` — *"attribute a delta by bracketing it with
two drift checks, never by inspecting the diff."*

### 0.2 Design-principle hardening (Phase 4.6 — honest)

Keyed against [`PRINCIPLE-INDEX.md`](../../../../dev-os/PRINCIPLE-INDEX.md) §2 on the same tuples:

- **Genchi Genbutsu** (`requirement × single-source/no-drift`) — applied and load-bearing. Every census
  row is a measured `--check` exit, not a doc claim. It is what caught navig8's CLAUDE.md asserting an
  `app/` that exists, and consumer #1's recipe failing while its pilot note reads green. Enforcer named
  (surfacing ≠ enforcement): the `--check` drift path itself is the gate, run twice per FR-3.
- **Mottainai** (`code·plan × idempotency/reuse`) — dominant constraint. This REQ adds **zero** onboarding
  grammar; FR-4 forbids SDK source changes in the pilot commit and makes that machine-checkable
  (`git diff src/startd8/backend_codegen/` must be empty). New keys here would fork the archetype.
- **Context-Correctness-by-Construction** (`code·plan × context-arrival/data-wiring`) — the FR-2
  collision rule is exactly this principle at the manifest seam: the checklist declares a slot
  (`empty_states: Entity`) whose create form may silently arrive without the fields that make the entity
  meaningful. Declared + validated, not assumed.
- **Ichigo Ichie** — the *most* on-point principle and it is **parked in §3**, advisory-only, because
  `lifecycle/bootstrap` names entry-points, not first-run *quality*. Cited as advisory and **not**
  returned by the keyed lookup. This REQ is a second concrete recurrence of that gap; it carries the
  standing extension request for `first-run/cold-start-quality` (the route Mieruka took to §2 in
  2026-07-24). Ratification belongs in `PATTERN-CATALOG.md` §1 first — not asserted here.

## Overview

The `onboarding:` archetype ships and is declared by two surfaces: an SDK test fixture and one lived
app that co-evolved with it. Neither is an independent adoption, so "portable" is currently an
untested generalization. This REQ picks a **third surface — a real product consumer that did not
co-evolve with the archetype** — and defines the gate that makes its adoption count as evidence:
baseline-green first, onboarding delta second, runtime smoke third, and a written verdict that is
allowed to say *no*. It invents no onboarding grammar; FR-1..6 of the archetype are cited, not
restated. The deliverable of the pilot is evidence about the archetype, not features for the app.

## Objectives

- O-1: A cascade consumer that never saw the archetype's development declares `onboarding:` and
  regenerates green with **zero SDK source changes**.
- O-2: The onboarding delta is **attributable** — separable from the consumer's pre-existing drift.
- O-3: The portability verdict is falsifiable and may be negative; a pilot that required SDK edits is
  recorded as a failed proof, not quietly repaired into a success.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Baseline drift (12–97 artifacts) swamps the onboarding delta, making "green" unattributable | FR-3 brackets the change with two `--check` runs; only *added* drift counts | high |
| quality | Pilot silently becomes archetype development — SDK edited to make the consumer work, then declared portable | FR-4 requires an empty `git diff` on `backend_codegen/` in the pilot commit; FR-7 forces a negative verdict if not | high |
| quality | Prior-consumer regression (household `dose`) means the baseline claim is already false | FR-8 blocks advancement until re-verified or filed with a dated gate | high |
| safety | UPL-sensitive consumer: orientation prose drifts into legal advice, or restates attorney-gate `validationStatus` | Trust boundary above; tips are navigation-only and reviewed against the UPL invariant; owned copy untouched | high |
| security | Welcome route counts rows across every declared `empty_states` entity | Inherited archetype mitigation — read-only counts, no write surface (cite; not re-specified) | medium |
| cost | Regenerating a 12-artifact-drifted app overwrites hand-tuned files | FR-3's recorded recipe must document the RESIDUAL set before any write; `--check` is read-only and runs first | medium |

## Profile

Declared profile: **internal**

## Candidate census (grounded 2026-08-14)

Every cascade consumer on disk — `schema.prisma` + `views.yaml` + a generated `app/`. Drift measured
by `startd8 generate backend --schema … --views … [--pages …] --human-inputs … --check` (read-only).

| Rank | Consumer | Path | Entities | Last commit | Drift today | Hand-built onboarding | Verdict |
|------|----------|------|----------|-------------|-------------|----------------------|---------|
| **1** | **navig8** | `~/Documents/dev/navig8` | 8 | 2026-08-13 `8cf1a22` | **12** | none | **SELECTED** |
| 2 | strtd8-v2-cascade | `~/Documents/dev/strtd8/strtd8-v2-cascade` | 16 | 2026-06-15 `517c4b2` | 84 | none found | fallback |
| 3 | benchmark reviewer portal | `~/Documents/dev/benchmarking/Summer2026/portal/internal` | 13 | 2026-08-12 `fe820e3` | 97 | **yes** — `app/reviewer_intro.py` + `/start` | rejected |
| 4 | strtd8 (v1) | `~/Documents/dev/strtd8/strtd8` | 31 | 2026-07-09 `8dfefb6` | not measured (no recipe; hand-built `control-panel/`) | control-panel | rejected |
| — | attorney portal | `~/Documents/dev/startd8-work/work/legal/attorney-portal` | n/a | — | not a cascade consumer (hand-built ONB v0.4) | yes | rejected — Non-goal |
| — | portal-v2 | `~/Documents/dev/benchmarking/Summer2026/portal-v2` | n/a | — | ineligible: no `prisma/` — its `views.yaml` is pipeline output | — | ineligible |

Worktrees, `tests/fixtures/wireframe/`, and `docs/design/wireframe/spike-*/manifests/` copies are
excluded: they are the harness (consumer #0), not independent adoptions.

**Why navig8.** Lowest drift by a factor of seven; freshest non-pilot commit; a genuinely different
domain (Michigan legal intake) and audience (laypeople) from household, which is the portability
signal we lack; no hand-built onboarding to fight; and its owned-field set clears FR-2 — all five
targets in `prisma/human_inputs.yaml` are verification-pipeline- or attorney-gate-owned
(`TreeNode.confidence`, `TreeNode.attorneyNote`, `LandmineEntry.confidence`,
`DecisionTree.validationStatus`, `SequenceConfig.validationStatus`), none of which a first-run user
types. First-run orientation is also product-critical there rather than decorative: the app must state
the UPL boundary and its `candidate — not yet attorney-validated` status up front, which is precisely
the content-not-modal shape PC-13 prescribes.

**Why not the portal.** It is the strongest candidate on entity count and is the one to revisit later,
but adopting it now means deleting a working hand-built `/start` in a live embargoed deployment while
reconciling 97 drifted artifacts — the attorney-portal failure mode with a new name.

## Functional requirements

- **FR-1 — The census is an artifact, not a claim.** This REQ carries a ranked table of every cascade
  consumer on disk, each row citing path, entity count, last commit, measured drift, and whether a
  hand-built onboarding surface exists. Touches: census.
  Verify: every drift number reproduces by re-running the command recorded in PLAN S1; a consumer that
  has `schema.prisma` + `views.yaml` + `app/` on disk and no row is a census defect. Serves: O-1

- **FR-2 — Owned-field collision disqualifies a candidate.** A candidate is rejected when any field a
  first-run user must type to create an `empty_states` entity is declared in that consumer's
  `human_inputs.yaml`, because owned fields are stripped from the generated form
  (`_writable_fields`, `htmx_generator.py:1407`). Touches: human_inputs manifest, empty_states keys.
  Verify: for the selected consumer, every declared `empty_states` entity's create form renders at
  least one required input; and `generate backend … --check` raises no
  `form_prose.yaml: … unknown form field` error. Serves: O-1

- **FR-3 — Baseline-green precedes the onboarding delta.** Before `onboarding:` is declared, record the
  consumer's exact regeneration recipe (flag set + a written RESIDUAL drift set) and reconcile baseline
  drift down to that residual. Touches: recipe, drift transcript.
  Verify: two `--check` transcripts bracket the change — a pre-declaration run whose drift equals the
  recorded residual, and a post-declaration run whose *added* drift is exclusively the three onboarding
  kinds (`fastapi-onboarding`, `onboarding-welcome`, `onboarding-aggregator`). Serves: O-2

- **FR-4 — Declare `onboarding:` with existing grammar only.** The consumer's block uses archetype
  FR-1/FR-2 keys and nothing else; the pilot introduces no SDK change. Touches: views.yaml,
  onboarding prose.
  Verify: the block parses with no edits under `src/startd8/backend_codegen/` — `git diff` on that
  path is empty for the pilot commit; any needed SDK change converts this pilot into a negative result
  under FR-7. Serves: O-1, O-3

- **FR-5 — Regeneration is green on the onboarding kinds.** After regen, the three onboarding artifact
  kinds are in sync and the tolerant mount is present. Touches: drift transcript, welcome.
  Verify: post-regen `--check` reports the three kinds in sync, and `app/main.py` contains the
  `onboarding_routers` try/except mount (present in household `app/main.py:129`, **absent** in navig8's
  today — its `main.py` predates FR-5). Serves: O-1, O-2

- **FR-6 — First-run smoke on the running app.** The welcome route works on an empty database and the
  checklist tracks real counts. Touches: welcome, empty_states keys.
  Verify: given an empty DB, GET the declared route returns 200 and its body contains each declared
  empty-state copy string and no `role="dialog"` / modal markup; after inserting one row of one
  declared entity, that entity's checklist item is gone and the others remain. Serves: O-1

- **FR-7 — The verdict is recorded and may be negative.** A short pilot note states what transferred
  unchanged, what needed consumer-specific work, and an explicit portability verdict. Touches: pilot note.
  Verify: the note exists beside this REQ, cites both FR-3 `--check` transcripts by command line, and
  contains one of `PORTABLE` / `PORTABLE-WITH-FRICTION` / `NOT-PORTABLE`; a pilot that required SDK
  edits reads `NOT-PORTABLE` and the archetype REQ's portability status is downgraded, not amended.
  Serves: O-3

- **FR-8 — Prior-consumer re-verification (survivorship pre-flight).** Consumer #1's recorded recipe is
  re-run before this pilot's verdict is written; the portability claim may not advance while it fails.
  Touches: recipe, drift transcript.
  Verify: household `make check`'s backend leg completes without a manifest error, **or** the current
  failure (`form_prose.yaml: entry 'Medication' references unknown form field 'dose'`, reproduced
  2026-08-14 on both `/opt/homebrew/bin/startd8` and the SDK venv) is filed as a dated Closure-Ledger
  gate and cited in the FR-7 note. Serves: O-3

## Non-goals

- **Attorney-portal retrofit** — hand-built ONB v0.4 in `startd8-work/work/legal/attorney-portal/`;
  cited as shape only, never adopted. Re-affirmed from the archetype's Non-goals.
- **Benchmark-portal `/start` retrofit** — replacing `app/reviewer_intro.py` and its role-aware
  onboarding in a live embargoed deployment. A separate REQ if ever wanted.
- New archetype features or grammar keys of any kind (FR-4 makes this machine-checkable).
- FK picker widgets (pilot P1-2) — separate REQ.
- Per-list CRUD empty-states (archetype v1 already excludes; separate REQ).
- Multi-step `confirm-walk:` cascade archetype.
- Welcome Mat / Concierge chat, download, or kickoff YAML export.
- `redirect_root_if_empty` exercise — navig8 has no `pages.yaml`; adding a pages layer to satisfy an
  optional flag is out of scope for a portability proof.
- **Fixing** the household `form_prose` / owned-field regression. FR-8 requires *observing and filing*
  it; the fix is its own loop.
- Any change under `src/startd8/backend_codegen/` (FR-4).

## Owned fields

Only humans enter: the selected consumer's `views.yaml` `onboarding:` prose — `title`, `lead`, `tips[]`,
`empty_states` copy, `nav_label` — and the FR-7 pilot-note verdict. For navig8 specifically, no
onboarding copy may state or paraphrase a `validationStatus`; that string is attorney-gate-owned per
`navig8/prisma/human_inputs.yaml` and is rendered verbatim by the app.

## Contract projection

- **Backend:** startd8-python-cascade
- **Vocabulary home (cite):** `src/startd8/backend_codegen/onboarding_manifest.py` +
  [`ONBOARDING_ARCHETYPE_REQUIREMENTS.md`](./ONBOARDING_ARCHETYPE_REQUIREMENTS.md) § Contract projection

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| welcome | page | structure | Generated GET orientation route on the selected consumer; kinds `fastapi-onboarding`, `onboarding-welcome`, `onboarding-aggregator` (`drift.py`), mounted by `crud_generator.render_main` |
| empty_states keys | entity | structure | Must exist on the consumer's `schema.prisma` |
| onboarding prose | page | words | Tips / lead / empty-state copy — human-authored, placeholder until reviewed |
| views.yaml | manifest | structure | Carries the `onboarding:` block; parsed by `onboarding_manifest.py`; drift-hashed |
| human_inputs manifest | manifest | structure | FR-2 collision source of truth |
| recipe | manifest | structure | Recorded flag set + RESIDUAL drift (household `Makefile` is the reference shape) |
| drift transcript | doc | structure | The bracketing `generate backend … --check` output pair (FR-3) |
| census | doc | words | The ranked candidate table above (FR-1) |
| pilot note | doc | words | FR-7 verdict artifact |

---

## Appendix A — Accepted (with where merged)

_(empty at v0.2 — no review round yet)_

## Appendix B — Rejected (with rationale)

- **Benchmark reviewer portal as the pilot consumer** — rejected during the v0.1→v0.2 planning pass.
  Highest entity count and a `pages.yaml` owning `/`, but 97 drifted artifacts, a live embargoed
  deployment, and an existing hand-built role-aware `/start`. Adopting it is an onboarding *retrofit*,
  which is the failure mode the archetype was defined to avoid. Recorded here so a later reviewer does
  not re-propose it without new evidence.
- **Adding a `pages.yaml` to navig8 to exercise `redirect_root_if_empty`** — rejected: it changes the
  consumer to suit the test, weakening the portability signal the pilot exists to produce.

## Appendix C — Incoming review rounds

_(none yet)_

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
