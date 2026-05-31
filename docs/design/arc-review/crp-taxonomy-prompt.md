# Convergent Review Prompt

**Generated:** 2026-05-31 16:53:44 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_ARTIFACT_TAXONOMY_PLAN.md` | 164 lines · 1342 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` | 486 lines · 4728 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/private/tmp/crp-focus-taxonomy.md` | 25 lines · 241 words |

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

### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

## Where we need reviewer input most

1. **Accidental complexity — does the design actually remove it?** The reflective pass claims the
   taxonomy is a *net simplification* (Appendix D: 11 items to remove; REQ-OAT-070 extension-by-table
   invariant). Stress-test that claim. Where could the two-axis model (category × orientation) itself
   become a new source of accidental complexity — e.g. the dispatch table, the lookup tables, the
   3-way coverage blend? Is anything over-abstracted for 5 categories where only 3 are implemented?

2. **Producer/consumer scope boundary.** REQ-OAT-031 was split: producer (emit generation_report +
   source_checksum, in THIS SDK module) vs consumer (auto-satisfy reuse, in plan-ingestion /
   cap-dev-pipe, out of scope). Is that boundary clean and complete? Does the producer emit *enough*
   for the consumer (checksum granularity, what determines staleness), without this module taking on
   reuse logic it shouldn't?

3. **Nested artifact_categories metadata backward-compat.** REQ-OAT-020/022 introduce a nested
   `artifact_categories` form with a derived flat `artifact_types` view. Is the migration safe for
   existing readers? Who else reads `artifact_types` (onboarding export, plan-ingestion)? Any
   ordering/precedence hazards in flatten? Is "declare, don't guess" (REQ-OAT-024) realistic given
   onboarding metadata is produced upstream (does it require a cap-dev-pipe change too)?

4. **Orientation-aware validation & coverage.** REQ-OAT-050/051/060/061/062: the bridge "both halves"
   scoring, the mixed recording/alerting split, and metric_coverage_human/system/bridge. Is the
   orientation taxonomy crisp enough to validate against, or are there ambiguous cases (runbook as
   human end of the bridge; recording-rule subset)? Does the 3-way composite blend distort the
   headline score in a misleading way?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_ARTIFACT_TAXONOMY_PLAN.md`  ·  **Size:** 164 lines · 1342 words

```markdown
# Observability Artifact Taxonomy — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.1 (paired with `OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` v0.3)
**Scope:** SDK modules — `src/startd8/observability/artifact_generator.py`,
`src/startd8/validators/observability_artifact_checks.py`,
`scripts/generate_observability_artifacts.py`. The auto-satisfy *consumer* (REQ-OAT-031b) is
plan-ingestion (cap-dev-pipe) and is **out of scope** here.
**Branch:** `feat/observability-followup-run007` (or a fresh `feat/observability-taxonomy`).

---

## Guiding principle — complexity-first ordering

The plan is ordered so the **distillation lands before the features**. Phase 0 removes free-standing
cruft; Phase 1 makes the two axes first-class (the keystone), which *collapses* three smells for
free; Phase 2 unifies the dispatch and scoring duplication. Only then (Phases 3–5) do the
category/orientation features land — cheaply, because the structure now supports them. Per
REQ-OAT-070, every phase extends a **table**, not control flow. The pass should **net-remove** lines.

```
Phase 0  Enabling cleanups (no behavior change)         D-6, D-8, D-9, D-10
Phase 1  Keystone: two axes first-class                 REQ-OAT-023; collapses D-2, D-4
Phase 2  Unify dispatch + scoring                       REQ-OAT-042, 050-dispatcher; D-1, D-5
Phase 3  Naming / ownership                             REQ-OAT-010/011/012/013, 021; D-2-final, D-10
Phase 4  Orientation-aware validation + 3-way coverage  REQ-OAT-050/051/060/061/062; D-3
Phase 5  Metadata declare-don't-guess + routing + report REQ-OAT-020/022/024/040/041/030/031a; D-7, D-11
Phase 6  (deferred, cross-repo) auto-satisfy consumer    REQ-OAT-031b  [plan-ingestion]
```

---

## Phase 0 — Enabling cleanups (no behavior change)

Pure refactors that lower the cost of every later phase. Each is independently shippable and
test-neutral (behavior identical).

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Delete dead `compute_service_composite` (+ `__all__` entry); remove the no-op `repair_gridpos` call in `_repair_and_validate`; drop the dangling comment | checks.py, artifact_generator.py | D-6 |
| 0.2 | Centralize the duplicated composite weights into one constants block; reference from both validator and generator | checks.py, artifact_generator.py | D-8 |
| 0.3 | Extract a shared **check-runner** (`run_checks(list[(code, passed: bool, msg)]) -> (passed, total, issues)`) + a base result dataclass; refactor `validate_dashboard/alerts/slo` onto it (behavior identical) | checks.py | D-9 (enables Phase 4) |
| 0.4 | Move the `--portal-persona=all` fan-out **inside** the generator; CLI calls the generator once | scripts, artifact_generator.py | D-10 |

**Validation:** full observability + validator + dashboard_creator suites green, byte-identical
artifact output on a fixture run (these are refactors).

---

## Phase 1 — Keystone: two axes first-class (REQ-OAT-023)

The single highest-leverage change.

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Add `_ARTIFACT_TYPE_TO_ORIENTATION` lookup (sibling of existing `_ARTIFACT_TYPE_TO_CATEGORY`) | artifact_generator.py |
| 1.2 | Add `category: str` + `orientation: str` to `ArtifactResult` (and `GenerationReport` grouping) | artifact_generator.py |
| 1.3 | Populate both **centrally**: in `_generate_one` and the ~5 non-`_generate_one` construction sites, from the two tables — not at 40 call sites | artifact_generator.py |
| 1.4 | Emit `category`+`orientation` in `_write_index` and `_write_quality_report` per-artifact records | artifact_generator.py |

**Collapses for free:** D-2 (bucket category-3 out of the `services` dict using `category`),
D-4 (replace the `if type in (...)` role-bucketing with `group_by(orientation)`).

**Validation:** every artifact record carries both fields; the run-007 fixture's quality report
no longer shows a `project` entry in `services`; coverage bucketing keyed on orientation.

---

## Phase 2 — Unify dispatch + scoring (REQ-OAT-042, 070; D-1, D-5)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | Replace the five dispatch mechanisms with **one dispatch table** keyed `(category, artifact_type) → (generator, output_prefix, scope=per-service|per-project)`; the orchestrator iterates the table | artifact_generator.py |
| 2.2 | Merge `_repair_and_validate` (triplet) and `_score_extended_artifacts` (extended) into **one** `(category, orientation)`-aware scoring dispatcher driven by a `type → validator/contract` table | artifact_generator.py, checks.py |

**Removes:** D-1, D-5. **Enforces:** REQ-OAT-070 (new type = one table row).
**Risk:** per-service vs per-project scope must be explicit in the table (resolved: cat 1
per-service; cat 2/3 per-project). **Validation:** same artifacts produced as before; suites green.

---

## Phase 3 — Naming / ownership (REQ-OAT-010/011/012/013, 021)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Rename `generate_capability_index` → `generate_observability_inventory`; type `capability_index` → `observability_inventory`; output `observability-inventory.yaml`; update `_IMPLEMENTED_ARTIFACT_TYPES`, exclusion set, docstring | artifact_generator.py + tests |
| 3.2 | **Revert the Finding-2 masquerade** (REQ-OAT-013): reshape the body from the `manifest_id/version/capabilities[]` software-feature schema to a category-nested **inventory** (services + per-category artifact paths/counts) | artifact_generator.py + tests |
| 3.3 | `capability_index` becomes a category-aware honest skip owned by onboarding (REQ-OAT-011/052) | artifact_generator.py |
| 3.4 | Split `portal` → `onboarding_portal` + `role_dashboard` (REQ-OAT-021); update the dispatch table + persona handling | artifact_generator.py, portal_spec_builder.py + tests |

**Validation:** no artifact named `capability_index` produced by observability; `observability-inventory.yaml`
validates as an inventory; the run-007 Finding-2 test is replaced by an inventory-schema test.

---

## Phase 4 — Orientation-aware validation + 3-way coverage (REQ-OAT-050/051/060/061/062; D-3)

Built on the Phase-0.3 check-runner, so the orientation branch is small.

| Step | Change | Files |
|------|--------|-------|
| 4.1 | Add `orientation` param to the validators; add the **bridge actionability** check (alert/loki: runbook/dashboard link + summary; notification_policy: non-null receiver/route) | checks.py |
| 4.2 | Split a `prometheus_rule`/`loki_rule` file into recording (system) vs alerting (bridge) subsets; score each; record the breakdown (REQ-OAT-062) | checks.py |
| 4.3 | Generalize coverage from 2 buckets to 3 orientations: `metric_coverage_human/system/bridge` (collect SLO/recording content as the system bucket); keep `…_dashboarded/_alerted` as aliases; 3-way composite blend; **service/project/agent only**, not pipeline-innate (REQ-OAT-051) | artifact_generator.py |
| 4.4 | Demote `dashboard_spec` to `status="intermediate"` so it is not written/scored as an end artifact (D-3); declare only `dashboard` (JSON) | artifact_generator.py + tests |

**Validation:** a valid-but-unactionable alert scores partial; a recording+alerting `prometheus_rule`
shows a 2-part breakdown; `metric_coverage_{human,system,bridge}` present; `artifacts_scored ==
artifacts_generated` still holds (Finding-1 invariant) with `dashboard_spec` no longer counted.

---

## Phase 5 — Metadata declare-don't-guess + routing + generation_report (REQ-OAT-020/022/024/040/041/030/031a; D-7, D-11)

| Step | Change | Files |
|------|--------|-------|
| 5.1 | `_declared_artifact_types` reads nested `artifact_categories` first, flat `artifact_types` as fallback; add `_flatten_artifact_categories` (REQ-OAT-020/022) | artifact_generator.py |
| 5.2 | Read declared **entry kind** (collapse `_is_non_service_entry` 7 heuristics → 1 check, name-pattern as recorded fallback) (REQ-OAT-024; D-7) | artifact_generator.py |
| 5.3 | Read declared **metric category/orientation**; route domain metrics to cat 4/5 surfaces (or record as "awaiting home"); heuristic fallback recorded as *inferred* (REQ-OAT-024/040/041) | artifact_generator.py |
| 5.4 | Once metric routing lands, **remove** the `_domain_alert_todo_block` stub machinery (D-11) | artifact_generator.py + tests |
| 5.5 | Emit `generation_report` (category-nested, per-artifact `{type, category, orientation, service, output_path, status, source_checksum}`) + link to `run-provenance.json` (REQ-OAT-030/031a) | artifact_generator.py |

**Validation:** nested + flat metadata both parse; a non-service entry with `kind` declared is
skipped without heuristics; cost/token metrics route off the service dashboard (or are recorded as
deferred); `generation_report` carries checksums; backward-compat flat view still emitted.

---

## Phase 6 — Auto-satisfy consumer (REQ-OAT-031b) — DEFERRED / cross-repo

Lives in **plan-ingestion (cap-dev-pipe)**, not these modules. Consumes the Phase-5
`generation_report` + checksums to auto-satisfy unchanged artifacts on serial / project-update runs
and emit a delta report. Tracked here only as the contract the Phase-5 producer must satisfy.

---

## Traceability (requirement → phase)

| REQ-OAT | Phase | REQ-OAT | Phase |
|---------|-------|---------|-------|
| 010/011 | 3 | 042 | 2 |
| 012/013 | 3 | 050 | 0.3 + 4 |
| 020/022 | 5 | 051 | 4 |
| 023 (keystone) | 1 | 052 | 1 + 3 |
| 024 | 5 | 060 | 1 |
| 021 | 3 | 061/062 | 4 |
| 030/031a | 5 | 070 | 2 (enforced) |
| 031b | 6 (deferred) | 040/041 | 5 |

Every REQ-OAT maps to a phase; every phase step traces to a REQ-OAT and/or an Appendix-D removal.

## Before-code checklist (per reflective-requirements Phase 6)

- [ ] Every v0.3 requirement has a plan step (above).
- [ ] Every plan step traces to a requirement or a D-item removal.
- [ ] No open questions remain (per-service/project dispatch + validator-location resolved in §0).
- [ ] Phases 0–2 net-remove lines before any feature lands (distillation-first).
- [ ] REQ-OAT-070 invariant holds after Phase 2 (new type = one table row, no new branch).

---

*Plan v0.1 — paired with requirements v0.3. Six phases; Phases 0–2 are distillation (remove
accidental complexity), 3–5 are the category/orientation features, 6 is the deferred cross-repo
consumer. Net line delta expected negative.*
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md`  ·  **Size:** 486 lines · 4728 words

```markdown
# Observability Artifact Taxonomy — Requirements

**Date:** 2026-05-31
**Status:** Draft v0.3 — post-planning self-reflective update (requirements only; no code this
pass). Two-axis model: artifact = (category = *what is observed*, orientation = *who consumes /
acts on it*).
**Lineage:** Consolidates and re-frames `OBSERVABILITY_GENERATION_GAP_ANALYSIS.md`,
`OBSERVABILITY_GENERATION_FOLLOWUP_RUN007.md`, `UNIFIED_OBSERVABILITY_MANIFEST_REQUIREMENTS.md`,
and the pipeline-innate concerns in `cap-dev-pipe/design/pipeline-requirements.md` (REQ-CDP-*).
**Owner module (future code):** `src/startd8/observability/artifact_generator.py` +
`src/startd8/validators/observability_artifact_checks.py`

---

## 0. Planning Insights (self-reflective update, v0.2 → v0.3)

> A planning pass read the three target modules (`artifact_generator.py` ~2400 lines,
> `observability_artifact_checks.py` ~1460 lines, the CLI) to map each requirement to code and
> to surface pre-existing accidental complexity. The headline finding: **this taxonomy is a net
> simplification.** Both axes (category, orientation), once carried as first-class fields, *dissolve*
> five separate accidental-complexity smells. The implementation removes more code-paths than it
> adds. Key corrections below; the opportunistic cleanups are catalogued in Appendix D.

| v0.2 assumption | Planning discovery | Impact on requirements |
|-----------------|--------------------|------------------------|
| REQ-OAT-023 (add category+orientation) is a heavy "L" touching ~40 call sites | Nearly all `ArtifactResult`s flow through `_generate_one` + ~5 helpers; with two lookup tables (`_ARTIFACT_TYPE_TO_CATEGORY` already exists; add `…_ORIENTATION`) assignment is centralized, not 40 hand-edits | 023 reframed as the **keystone** (M, not L); it *unblocks* 020/040/042/051/052 and dissolves the role-bucketing + pseudo-service smells |
| REQ-OAT-040 metric routing is a generation concern | As written it forces brittle name-pattern heuristics (`if "startd8_" in name`) — **new** accidental complexity | **NEW REQ-OAT-024 + revised 040: declare, don't guess** — metadata carries each metric's category/orientation; heuristics are fallback only |
| `_is_non_service_entry` (7 heuristics) is just existing cruft | Same "guessing what metadata should declare" anti-pattern as 040 | Folded into REQ-OAT-024 (structural classification in metadata collapses 7 heuristics → 1 check) |
| REQ-OAT-031 (auto-satisfy) is one requirement for this module | The generator's only job is to **emit** `generation_report` + checksums; the **reuse/auto-satisfy** logic lives in plan-ingestion (cap-dev-pipe), out of this module | 031 **split**: producer (emit, in scope) vs consumer (auto-satisfy, cross-referenced, out of scope) |
| REQ-OAT-013 "migrate the Finding-2 conformant output" | The run-007 Finding-2 fix made `capability_index` *masquerade* as the software-feature schema — the **wrong** direction; it must be reverted, not migrated | 013 reframed as **revert-the-masquerade** → inventory schema |
| REQ-OAT-050 (orientation-aware validation) is "L" | The structural validators are ~90% boilerplate and already near-ready (alerts already check service-label/summary); adding an `orientation` param + a bridge-actionability check is small **once** the 3 validators share a check-runner | 050 is **S–M**; gated on an enabling refactor (unify the 3 boilerplate validators) that itself removes complexity |
| Extensibility was implicit | Five parallel dispatch mechanisms + two parallel scoring paths mean "add an artifact type" currently means "add control flow" | **NEW REQ-OAT-070 invariant**: adding a type MUST be declarative table entries (type→category/orientation/generator/validator), never new dispatch/validation branches |

**Resolved questions:**
- **Per-service vs per-project dispatch (was ambiguous).** Category 1 is per-service; categories 2
  & 3 are per-project (single call, may read all services). Categories 4 & 5 reserved. This is
  now stated in REQ-OAT-042.
- **Where does validator work live?** REQ-OAT-050/061/062 are `observability_artifact_checks.py`
  changes; REQ-OAT-023/040/042/051 are `artifact_generator.py`; auto-satisfy consumer is
  plan-ingestion. Scope boundaries are now explicit per requirement.

*The essential complexity is two declarative axes + two lookup tables + one dispatch table + one
validation runner. Everything else is accidental and collapses (Appendix D).*

---

## 0.1 Motivation

ContextCore generation today treats every produced artifact as one **flat list**:
`onboarding-metadata.json.artifact_types` is a flat enumeration, the generator runs all
types in a single loop, quality scoring applies uniform structural validators, and the
generation manifest records artifacts with no category dimension. This flat treatment is
the root of a recurring class of "looks-like-success" failures (run-003 Gaps 1–5, run-007
Findings 1–3): artifacts of fundamentally different *kinds* are produced, scored, and
reported as if they were the same thing.

Conceptually, every artifact is classified on **two independent axes**:
**category** (§1.1 — *what is observed*: service / business / pipeline-innate / project / agent)
and **orientation** (§1.2 — *who consumes & acts on it*: human, e.g. a dashboard; system, e.g.
a metric / SLI / SLO; or bridge, e.g. an alert or notification policy — system-evaluated,
human-actioned). The flat list collapses both axes, which is why artifacts of fundamentally
different kinds get produced, scored, and reported as if the same. This document defines the
two-axis taxonomy, fixes the `capability_index` naming collision, specifies a category-nested
metadata structure, and defines the pipeline-innate artifact-reuse contract that serial /
project-update runs need.

This is a **requirements** document. Code alignment is a separate, follow-up pass.

---

## 1. The five-category taxonomy

| # | Category | Observes / records | Example artifact types | Deploy target | Status |
|---|----------|--------------------|------------------------|---------------|--------|
| 1 | **Service Observability** | a running **service's** health (RED, infra) | `prometheus_rule`, `dashboard`, `slo_definition`, `loki_rule`, `notification_policy`, `service_monitor` | Prometheus / Grafana / Loki / Alertmanager / k8s | Implemented |
| 2 | **Business Observability** | **business outcomes & role views** | `onboarding_portal`, `role_dashboard` | Grafana (audience-scoped) | Partial (portal conflates the two) |
| 3 | **Pipeline / Innate** | the **generation run itself** | `provenance`, `generation_report` (run/generation index), `observability_inventory` | internal (pipeline state) | Implicit / undocumented |
| 4 | **Project Observability** | the **project's development lifecycle** | (reserved) task-progress, burndown, delivery, code-quality | Grafana (project tracking) | Reserved — signals emitted, no generator |
| 5 | **AI Agent Observability** | the **AI agents / LLM workflows** | (reserved) cost, tokens, sessions, agent-trace, eval/quality | Grafana / Tempo (agent telemetry) | Reserved — signals emitted, no generator |

The discriminator is **"whose telemetry / what subject is this?"**:

- (1) Service = the *deployed application at runtime*.
- (4) Project = *building & maintaining* that application.
- (5) AI Agent = the *agents that build it*.
- (2) Business = *outcomes and audiences*.
- (3) Pipeline/Innate = *bookkeeping about the generation process* — it is not "observability
  of" a subject; it records **what was generated** so later stages/runs can reason about it.

### 1.1 Category definitions

**1 — Service Observability.** Per-service technical monitoring derived from OTel convention
metrics × business SLO thresholds. This is the existing triplet (`alert_rule`/`prometheus_rule`,
`dashboard`(+spec), `slo_definition`) plus the extended technical types (`service_monitor`,
`loki_rule`, `notification_policy`). Subject: a deployed service. **Must contain only
service-health signals** — see REQ-OAT-040 on metric routing.

**2 — Business Observability.** Audience- and outcome-oriented views. Split into two distinct
artifact types (REQ-OAT-021): `onboarding_portal` ("what *is* this project / what services
exist") and `role_dashboard` ("what does my role — operator / engineer / manager — need to do
now"). A meta-layer over category 1, not a replacement for it.

**3 — Pipeline / Innate.** Records the generation run. Comprises: `provenance`
(`run-provenance.json`, input→output checksum linkage, REQ-CDP-INT-001); `generation_report`
(a run/generation index of *what was produced* across all categories, enabling project-update
and serial-run coordination — REQ-OAT-030/031); and `observability_inventory` (operator-facing
index of the observability artifacts specifically — the artifact currently mislabeled
`capability_index`, REQ-OAT-012). These are **not** "observability of" a subject; they are
generation metadata.

**4 — Project Observability (reserved).** Observes the *development lifecycle* of the project
being built: task progress, burndown/velocity, delivery and code-quality. Aligns with the
ContextCore "Project O11y / tasks-as-spans" paradigm. **Reserved**: no generator yet, but the
signals already exist (REQ-OAT-041).

**5 — AI Agent Observability (reserved).** Observes the *AI agents and LLM workflows* doing
the work: cost, token burn, active sessions, context-usage, truncations, agent traces, tool
use, eval/quality. **Reserved**: no generator yet; the SDK already emits these metrics
(`costs/`, session tracking) (REQ-OAT-041).

### 1.2 Second axis — artifact orientation (consumer)

Category (§1.1) answers *"what is observed."* It does **not** capture *"who consumes the
artifact and who acts on it,"* which is an independent property. A service dashboard and a
service SLO are both category-1, but a human reads the dashboard while a machine evaluates the
SLO — they need different generation inputs, different validation, and different coverage
accounting. **Orientation** is therefore a second, orthogonal axis. Every artifact is
classified on **both** axes: `(category, orientation)`.

| Orientation | Primary consumer | Artifact types | Validated for |
|-------------|------------------|----------------|---------------|
| **Human-oriented** | a **person** reads / interprets it | `dashboard`, `onboarding_portal`, `role_dashboard`, `runbook` | clarity, completeness, layout, audience-fit, navigability |
| **System-oriented** | a **machine** consumes it | `slo_definition` (SLI + SLO), `service_monitor` (metric collection), recording rules, `provenance`, `generation_report`, `observability_inventory` | schema correctness, parseability, threshold / indicator validity |
| **Bridge (both)** | system-**evaluated**, human-**actioned** | `prometheus_rule` / `alert_rule` (alerting), `loki_rule` (alerting), `notification_policy` | **both** sides: rule validity (system) **and** actionability — severity, annotations, runbook/dashboard links, routing target (human) |

**Why orientation is its own axis (granularity & tracking):**

- **Bridge artifacts are where the system→human handoff happens.** An alert that is
  syntactically valid (system ✓) but has no actionable annotation, no runbook/dashboard link,
  or no notification route (human ✗) is *half-broken* in a way neither a pure-system nor a
  pure-human check would catch. Classifying alerts and notification policies as **bridge** lets
  validation assert **both** halves, and lets reporting track the handoff explicitly.
- **It generalizes the run-007 coverage split.** "dashboarded vs alerted" was an early,
  ad-hoc instance of this axis: *dashboarded* = on a **human** surface; *alerted* = on a
  **bridge** surface. Orientation makes this a principled, complete dimension — a metric's
  coverage is tracked across **human / system / bridge** surfaces (REQ-OAT-061), so a metric
  that is visualized but neither defined as an SLI nor alerted is visibly only 1/3 covered.
- **Mixed-orientation files are explicit.** A `prometheus_rule` / `loki_rule` file may contain
  *recording* rules (system) and *alerting* rules (bridge). The artifact's orientation is
  **bridge-primary**; its recording-rule subset is scored on the system dimension
  (REQ-OAT-062). This is recorded, not hand-waved.

---

## 2. The `capability_index` disambiguation

`capability_index` (and `.agent.yaml`, "capability index") currently names **four distinct
concepts**. This collision is the single largest source of accidental complexity in the
generation layer. The decisions below (adopted) disentangle them.

| # | Concept | Schema / shape | Owner | Decision |
|---|---------|----------------|-------|----------|
| (a) | `/capability-index` skill + `docs/capability-index/startd8.sdk.capabilities.yaml` — manifest of the **software's features** | `manifest_id`/`version`/`capabilities[]` (capability_id, category, maturity, summary, evidence) | startd8-sdk | **Keep** the name `capability_index` |
| (b) | Onboarding contract `artifact_types.capability_index` → `docs/capability-index/contextcore.agent.yaml` — **software features** (same concept as (a)) | same as (a); `schema_url: contextcore.io/schemas/capability-index/v1` | ContextCore export / onboarding | **Cede**: this is the canonical `capability_index`; the observability generator does **not** produce it |
| (c) | Observability generator's `generate_capability_index` output — actually an **observability inventory** | currently ad-hoc `{observability_capabilities, …}` (or, post run-007 Finding 2, a *masquerade* of (a)) | startd8-sdk observability | **Rename → `observability_inventory`** (category 3); stop calling it `capability_index` |
| (d) | The **generation index** intent: index of *what was generated*, for project-update / serial-run reuse | new — `{run_id, generated_at, categories: {…}, artifacts: […], provenance_links}` | none yet | **Formalize → `generation_report`** (category 3) |

**REQ-OAT-010.** The observability generator MUST NOT produce an artifact named
`capability_index`. The `capability_index` concept (a/b) is owned by the onboarding /
ContextCore export path (REQ-CDP-ONB-001) and describes software features, not observability.

**REQ-OAT-011.** When `capability_index` appears in a project's declared artifact requirements
but is owned by onboarding, the observability generator MUST report it via the honest-skip
mechanism (category-aware, REQ-OAT-052) — i.e. *not produced here, owned by onboarding* —
rather than emitting a wrongly-schemaed file.

**REQ-OAT-012.** The observability generator's inventory of the observability artifacts it
produced MUST be named `observability_inventory` and emitted to
`observability-inventory.yaml`. It belongs to category 3 (pipeline/innate). Its schema is an
inventory (services, artifact counts/paths by category), explicitly **not** the
`capability_index` schema. (This reverses run-007 Finding 2 Option A.)

**REQ-OAT-013 (revert the masquerade).** The run-007 Finding-2 change made the obs generator's
`capability_index` *conform to the software-feature schema* (`manifest_id`/`version`/`capabilities[]`)
— i.e. it made an observability inventory **masquerade** as a capability manifest. Planning
confirmed this was the wrong direction. The code-alignment pass MUST **revert the masquerade**:
reshape the output to a category-3 **inventory** schema (services + per-category artifact
list/counts/paths) and rename to `observability_inventory` (REQ-OAT-012). It is not a migration
of a correct artifact; it is the removal of a wrong one.

---

## 3. Category-nested metadata structure

**REQ-OAT-020.** `onboarding-metadata.json` MUST group artifact declarations by category under
an `artifact_categories` key, replacing the flat `artifact_types` enumeration as the
authoritative form:

```yaml
artifact_categories:
  service_observability:
    artifact_types: { prometheus_rule: {...}, dashboard: {...}, slo_definition: {...},
                      service_monitor: {...}, loki_rule: {...}, notification_policy: {...} }
  business_observability:
    artifact_types: { onboarding_portal: {...}, role_dashboard: {...} }
  pipeline_innate:
    artifact_types: { provenance: {...}, generation_report: {...}, observability_inventory: {...} }
  # project_observability:  (reserved)
  # ai_agent_observability: (reserved)
```

Each `artifact_types.<type>` entry keeps its existing fields (`output_path`, `output_ext`,
`schema_url`, `expected_output_contracts`, `parameter_keys`, …).

**REQ-OAT-021.** Business observability MUST be represented as two distinct types —
`onboarding_portal` and `role_dashboard` — not a single `portal` type.

**REQ-OAT-022 (backward compatibility).** A flat `artifact_types` view MUST remain derivable
from `artifact_categories` (union of all categories' types) so existing readers do not break
during migration. Producers SHOULD emit both during the transition; the nested form is
authoritative.

**REQ-OAT-023 (keystone).** Every emitted artifact record (`ArtifactResult`, and entries in the
generation manifest / `generation_report`) MUST carry an explicit `category` field (five-category
enum) **and** an `orientation` field (`human` | `system` | `bridge`). The two are independent;
both are required. These fields MUST be assigned from two declarative lookup tables
(`_ARTIFACT_TYPE_TO_CATEGORY` — already exists; `_ARTIFACT_TYPE_TO_ORIENTATION` — new), populated
centrally (in `_generate_one` and the handful of non-`_generate_one` construction sites), **not**
hand-set at each call site. This requirement is the **keystone**: it unblocks REQ-OAT-020, 040,
042, 051, 052, and is the prerequisite that lets the accidental-complexity cleanups in Appendix D
(D-2 pseudo-service, D-4 role-bucketing) collapse declaratively.

**REQ-OAT-024 (declare, don't guess — structural classification in metadata).** The onboarding
metadata MUST carry the structural facts the generator currently reverse-engineers via heuristics,
so the generator reads them instead of guessing:
- **Entry kind.** Each `instrumentation_hints` entry MUST declare whether it is a real service
  (e.g. `kind: service`). This collapses the seven-heuristic `_is_non_service_entry` filter
  (Appendix D-7) into a single check.
- **Metric category & orientation.** Each declared metric (`manifest_declared[]`, and ideally
  `convention_based[]`) MUST carry its `category` (service / project / agent) and MAY carry
  `orientation`, so metric routing (REQ-OAT-040) is a lookup, not a name-pattern heuristic.

Name-pattern heuristics MAY remain only as a **fallback** when the metadata omits the
classification, and when used MUST be recorded in the generation report as an *inferred* (not
declared) classification, so the gap is visible. This requirement exists because planning showed
REQ-OAT-040, implemented naively, would *add* accidental complexity (brittle metric-name lists);
declaring the facts upstream removes it.

---

## 4. Functional requirements

### 4.1 Category-aware generation

**REQ-OAT-040 (metric routing).** Generation MUST route metrics to the category that owns them,
not dump all metrics onto category-1 service dashboards. Specifically the `manifest_declared`
domain metrics MUST route as:

| Metric | Category |
|--------|----------|
| `startd8_cost_total`, `startd8_tokens_total`, `startd8_active_sessions`, `startd8_context_usage_ratio`, `startd8_truncations_total`, `startd8_requests_total`, `startd8_response_time_ms` | 5 — AI Agent Observability |
| `contextcore_task_progress`, `contextcore_task_status`, `contextcore_install_completeness_percent` | 4 — Project Observability |
| `http.server.*` / convention RED metrics | 1 — Service Observability |

The routing key MUST come from the metric's **declared** category (REQ-OAT-024), not a hardcoded
metric-name list; a name-pattern heuristic is a recorded fallback only. Until categories 4 & 5
have generators (reserved), these metrics MAY remain on a clearly-labeled "domain metrics"
surface, but the generation report MUST record that they are category-4/5 signals awaiting a
category-4/5 home (REQ-OAT-041), so the gap is visible rather than silently mixed into service
observability.

**REQ-OAT-041 (reserved categories).** Categories 4 and 5 MUST be defined and namespaced now,
with no generator required. The taxonomy and metadata MUST accept `project_observability` and
`ai_agent_observability` categories so that (a) their already-emitted metrics have a declared
home, and (b) future generators slot in without re-litigating the taxonomy.

**REQ-OAT-042 (orchestration).** The generator orchestrator SHOULD dispatch by category
(service / business / pipeline-innate), not run all types in one undifferentiated loop, so each
category can have its own preconditions, deploy path, and validators.

### 4.2 Category- and orientation-aware quality validation

**REQ-OAT-050.** Quality validation MUST be both **category-aware and orientation-aware**. Every
generated artifact MUST be scored (closing run-007 Finding 1: `artifacts_scored ==
artifacts_generated`), using validators appropriate to its `(category, orientation)`:
- **human-oriented** → clarity / completeness / layout / audience-fit (e.g. dashboard has the
  expected panels & navigation; runbook has all required sections);
- **system-oriented** → schema correctness / parseability / definition validity (e.g. SLO has a
  valid SLI + target; service_monitor has selector/endpoints);
- **bridge** → **both** halves: the rule is valid (system) **and** actionable (human) — severity
  set, summary/annotations present, runbook/dashboard links resolvable, a notification route
  exists. A bridge artifact that passes only one half MUST score as partial, not complete.

> **Feasibility (planning insight).** This is **S–M**, not L: the structural validators
> (`validate_dashboard/alerts/slo`) already perform most system checks and some human checks
> (alerts already verify the `service` label and `summary` annotation). The new work is an
> `orientation` parameter + a small bridge **actionability** check (runbook/dashboard link, a
> non-null notification receiver). It SHOULD be preceded by the enabling refactor in Appendix D-9
> (extract a shared check-runner from the three ~90%-boilerplate structural validators), which
> *removes* complexity and makes the orientation branch trivial.

**REQ-OAT-051 (orientation-based metric coverage).** Per-metric coverage MUST be tracked across
the orientation axis, generalizing the run-007 dashboarded/alerted split:
- `metric_coverage_human` — referenced by a live human surface (dashboard panel);
- `metric_coverage_system` — defined as a system artifact (SLI / recording rule);
- `metric_coverage_bridge` — referenced by an active (non-commented) alert / notification path.

`metric_coverage_human` ≡ the prior `metric_coverage_dashboarded`; `metric_coverage_bridge` ≡
the prior `metric_coverage_alerted` (names retained as aliases for continuity). All three fold
into the composite so a metric that is *visualized but neither SLI'd nor alerted* reads as
partially covered, not 1.0. These are **service / project / agent** observability dimensions and
MUST NOT be applied to pipeline-innate artifacts.

**REQ-OAT-052 (category-aware honest skip).** Coverage reporting MUST be reported per category.
A declared-but-unproduced type MUST be reported as a skip **with its category and owner** (e.g.
`capability_index — owned by onboarding, not produced by observability`), not as a generic
unimplemented type.

### 4.3 Orientation axis

**REQ-OAT-060.** Every artifact type MUST declare an `orientation` (`human` | `system` |
`bridge`) per the §1.2 table. Orientation is independent of category; generation, validation,
and reporting MUST treat the two axes separately.

**REQ-OAT-061.** Bridge artifacts (`prometheus_rule`/`alert_rule` alerting, `loki_rule`
alerting, `notification_policy`) MUST be validated and reported on **both** the system and human
sub-dimensions (REQ-OAT-050), so the system→human handoff (a valid alert that is nonetheless
unactionable, or a route with no target) is independently visible.

**REQ-OAT-062 (mixed-orientation files).** When a single artifact file contains rules of
differing orientation (e.g. a `prometheus_rule` with both recording and alerting rules), the
artifact's declared orientation is its primary one (bridge), and validation MUST additionally
score the off-orientation subset (recording rules on the system dimension). The breakdown MUST
be recorded, not collapsed.

### 4.4 Extensibility invariant (anti-accidental-complexity)

**REQ-OAT-070 (extension by table, not by control flow).** Adding a new artifact type MUST be
expressible as **declarative table entries** — `type → category`, `type → orientation`,
`type → generator`, `type → validator/contract`, `type → output_path` — and MUST NOT require new
branches in the orchestrator's dispatch or the validator's scoring. This invariant is the
permanent guard against the accidental complexity Appendix D removes (five dispatch mechanisms,
two scoring paths): once dispatch and validation are table-driven, the cost of a new type is one
row, and the taxonomy cannot silently re-accrete special-case control flow. Any change that would
add a per-type `if/elif` branch to orchestration or scoring is a violation of this requirement and
MUST instead extend the relevant table.

### 4.5 Pipeline-innate: generation index, reuse, and serial runs

**REQ-OAT-030 (`generation_report`).** The pipeline MUST emit a `generation_report` (category 3)
that indexes *what was generated this run*, grouped by category, with per-artifact
`{type, category, service, output_path, status, checksum?}` and links to the run provenance.
This is the artifact the user described as "a capability index that indexes what has been
generated."

> **Scope split (planning insight).** REQ-OAT-031 has a **producer** half and a **consumer** half.
> The producer half — emit `generation_report` with per-artifact source checksums — lives in this
> SDK module (`generate_observability_artifacts` + `_write_index`) and is **in scope** for the
> code-alignment pass. The consumer half — the auto-satisfy reuse logic below — lives in
> **plan-ingestion (cap-dev-pipe)** and is **out of scope** for this SDK module; it is specified
> here as a cross-referenced contract the producer must satisfy. The checksums exist solely for
> the consumer; this module has no use for them itself.

**REQ-OAT-031a (producer — in scope).** `generation_report` MUST record, per artifact, a
`source_checksum` derived from the inputs that determined it (onboarding metadata + manifest),
so a later run can detect staleness without re-deriving the artifact.

**REQ-OAT-031b (consumer — plan-ingestion, cross-referenced).** When a pipeline run targets
a project that was previously generated, plan-ingestion MUST load the prior
`generation_report` / `run-provenance.json` artifact inventory and, before requesting
generation:
1. match required artifacts (from the requirement/coverage contract) against the prior inventory;
2. mark already-present artifacts `auto-satisfy: true` (skip regeneration) when fresh
   (source-checksum unchanged);
3. mark changed/missing artifacts for (re)generation;
4. emit a **delta report** (new / updated / preserved) so serial runs are auditable.

This realizes the Mottainai principle (no needless regeneration) and is the contract that the
"more than one PrimeContractor run in series" and "update an existing project" use cases depend
on. (Folds the workflow review's proposed REQ-CDP-INT-008/009 into this taxonomy.)

**REQ-OAT-032 (intent direction).** Requirements MUST state which artifact is authoritative for
each direction of intent: the requirement/coverage contract (CRD-style) declares **what is
needed** (prospective); `generation_report` / `observability_inventory` record **what was
produced** (retrospective). Coverage = needed vs produced. These MUST NOT be conflated.

---

## 5. Migration & backward compatibility

- **M1.** Introduce `artifact_categories` (REQ-OAT-020) alongside a derived flat `artifact_types`
  view (REQ-OAT-022). No hard break for existing readers.
- **M2.** Rename observability `capability_index` → `observability_inventory` (REQ-OAT-012/013).
  The obsolete `capability_index` output is removed from the observability generator's declared
  types.
- **M3.** Split `portal` → `onboarding_portal` + `role_dashboard` (REQ-OAT-021).
- **M4.** Add `category` to `ArtifactResult` / generation manifest (REQ-OAT-023).
- All migrations are code-alignment work for the **follow-up pass**; this document defines the
  target behavior only.

---

## 6. Out of scope (this pass)

- Implementing category-4 (project observability) and category-5 (AI agent observability)
  generators. They are **reserved/defined** here; implementation is future work.
- The content hardening of category-1 extended scaffolds (notification webhook, loki rate
  gating, runbook sections) — tracked in the run-007 appendix; surfaced by REQ-OAT-050 scoring.
- Any code changes. This is requirements-only.

---

## Appendix A — current artifact type → (category, orientation) map

| Current type (code) | Category | Orientation | Notes |
|---------------------|----------|-------------|-------|
| `alert_rule` / `prometheus_rule` | 1 service | **bridge** | alerting = bridge; recording-rule subset scored on system (REQ-OAT-062) |
| `dashboard` (Grafana JSON), `dashboard_spec` (YAML intermediate) | 1 service | **human** | spec is an intermediate, not a declared type |
| `slo_definition` | 1 service | **system** | SLI + SLO target = machine-consumed |
| `service_monitor` | 1 service | **system** | metric-collection (scrape) config |
| `loki_rule` | 1 service | **bridge** | alerting = bridge; recording subset = system |
| `notification_policy` | 1 service | **bridge** | system routing → human delivery |
| `runbook` | 1 service (incident response) | **human** | borderline category; stays with service for now |
| `portal` (today) | 2 business | **human** | → split into `onboarding_portal` + `role_dashboard` |
| `capability_index` (today, obs generator) | 3 pipeline-innate | **system** | → **rename** to `observability_inventory` |
| `provenance` (`run-provenance.json`) | 3 pipeline-innate | **system** | |
| (new) `generation_report` | 3 pipeline-innate | **system** | what-was-generated index |
| `capability_index` (onboarding, software features) | n/a observability | — | owned by onboarding/ContextCore; ceded |

## Appendix B — requirement ID index

`REQ-OAT-010..013` naming/disambiguation · `REQ-OAT-020..023` metadata structure (category +
orientation fields) · `REQ-OAT-030..032` pipeline-innate / reuse · `REQ-OAT-040..042`
category-aware generation · `REQ-OAT-050..052` category- & orientation-aware validation ·
`REQ-OAT-060..062` orientation axis.

## Appendix C — the two axes at a glance

```
                      ORIENTATION  (who consumes / acts)
                  human            system           bridge
              ┌───────────────┬───────────────┬───────────────────┐
   1 service  │ dashboard     │ slo, svc_mon  │ alert, notif_policy│
   2 business │ portal, role  │ —             │ —                  │
C  3 pipeline │ —             │ provenance,   │ —                  │
A             │               │ gen_report,   │                   │
T             │               │ obs_inventory │                   │
E  4 project  │ (reserved)    │ (reserved)    │ (reserved)        │
G  5 agent    │ (reserved)    │ (reserved)    │ (reserved)        │
              └───────────────┴───────────────┴───────────────────┘
   (runbook = service × human; recording-rule subset of alert/loki = service × system)
```

## Appendix D — pre-existing accidental complexity to eliminate (opportunistic)

The planning pass catalogued accidental complexity that has accrued across the Gap 1–5 / Closure
3B / run-007 work. The taxonomy code-alignment pass SHOULD remove these opportunistically — most
*collapse for free* once the two axes (REQ-OAT-023) are first-class. "Adds/removes" is relative
to the codebase, not the requirements. Effort S/M/L.

| # | Smell | Location (artifact_generator.py unless noted) | Why accidental | Distillation | Effort |
|---|-------|-----------------------------------------------|----------------|--------------|--------|
| D-1 | **Five parallel dispatch mechanisms** (triplet loop, extended dict loop, dashboard-JSON convert, portal, capability_index) all produce `ArtifactResult` yet each has bespoke control flow | orchestrator `generate_observability_artifacts` | uniform problem, five shapes; adding a type means picking a mechanism | one **category-aware dispatch table** (REQ-OAT-042/070) | M |
| D-2 | **capability_index as project pseudo-service** — emitted with `service_id=project_id`, so the quality report's `services` dict gets a fake "service" with a spurious composite | `generate_capability_index`; `_write_quality_report` | shortcut to reuse the per-service loop; semantic lie | bucket category-3 artifacts in a separate `pipeline`/`project` report section (REQ-OAT-052); collapses once `category` exists | S |
| D-3 | **`dashboard_spec` vestigial intermediate** — the YAML spec is persisted *and scored* as an end artifact though it only feeds the Grafana-JSON conversion | `generate_dashboard_spec`, `_convert_dashboards_to_grafana_json`, `_CAPABILITY_INDEX_EXCLUDE` | the JSON was added later (Gap 4); the spec was never demoted | mark `status="intermediate"` (skip write/scoring) or inline it; declare only `dashboard` (JSON) | M |
| D-4 | **Role-bucketing by artifact-type name** (`if type in ("dashboard_spec","dashboard")` → dashboarded; `=="alert_rule"` → alerted) | `_write_quality_report` | conflates *type* with *orientation*; breaks when types multiply | declarative `group_by(orientation)` once `orientation` exists (REQ-OAT-051) | S |
| D-5 | **Two parallel scoring paths** — `_repair_and_validate` (triplet, rich validators, if/elif) vs `_score_extended_artifacts` (generic substring, separate pass) | both functions | triplet existed first; extended bolted on for run-007 Finding 1 | one `(category,orientation)`-aware scoring dispatcher (REQ-OAT-050) | M |
| D-6 | **Dead/inert code**: `compute_service_composite` exported in `__all__` but never called; `repair_gridpos` call is a no-op since gridPos is stamped at generation; dangling `compute_service_composite` comment | `observability_artifact_checks.py:645,36`; `artifact_generator.py` gridpos path | superseded by later fixes, never removed | delete | S |
| D-7 | **`_is_non_service_entry` seven heuristics** (req-id, run-id, project-name, dir-names, suffixes, multi-word…) | `_is_non_service_entry` | metadata doesn't declare entry kind, so the code guesses | one check on declared `kind` (REQ-OAT-024) | S |
| D-8 | **Duplicated magic weights** `_STRUCTURAL_WEIGHT/_COVERAGE_WEIGHT` in the validator **and** `_COMPOSITE_*_WEIGHT` in the generator; hardcoded default thresholds | `observability_artifact_checks.py:641`, `artifact_generator.py:~149,~2146` | copy-paste; can drift | one shared constants block | S |
| D-9 | **Three structural validators are ~90% boilerplate** (same parse / count / issues / repair pattern) across `validate_dashboard/alerts/slo`; 5 near-identical result dataclasses | `observability_artifact_checks.py` | grew one-at-a-time | extract a shared **check-runner** + base result; *enables* REQ-OAT-050 cheaply | M |
| D-10 | **CLI `--portal-persona=all` special branch** bifurcates the CLI and re-loads metadata (`load_onboarding_metadata`/`extract_service_hints`/`load_business_context` a second time) | `scripts/generate_observability_artifacts.py` | special case leaked into the CLI | move the persona fan-out inside the generator; CLI stays flat | S |
| D-11 | **`TODO-when-absent` domain-alert stub machinery** (`_domain_alert_todo_block`) becomes obsolete once domain metrics route to categories 4/5 (REQ-OAT-040) | `_domain_alert_todo_block`, alert assembly | workaround for "no home for domain metrics" | remove when metric routing lands | M |

**Net:** D-2/D-4/D-7 collapse *for free* with the REQ-OAT-023 keystone + REQ-OAT-024 metadata.
D-6/D-8/D-10 are standalone quick wins (do anytime). D-9 is an enabling refactor that *lowers* the
cost of REQ-OAT-050. D-1/D-5 are the two structural unifications that REQ-OAT-042/050/070 mandate.
The code-alignment pass should net **remove** lines, not add them.

---

*v0.3 — Post-planning self-reflective update. Reframed 1 keystone (023), added 2 requirements
(024 declare-don't-guess, 070 extension-by-table), split 1 (031 → producer/consumer), corrected 2
(013 revert-not-migrate, 050 effort S–M), resolved 2 questions, and catalogued 11 pre-existing
accidental-complexity items (Appendix D) the implementation should remove. Net finding: the
taxonomy is a simplification — implementation removes more complexity than it adds.*
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
