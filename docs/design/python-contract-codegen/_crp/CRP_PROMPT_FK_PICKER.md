# Convergent Review Prompt

**Generated:** 2026-08-14 16:16:56 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per \`CONVERGENT_REVIEW_AGENT_GUIDE.md\`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 12 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/FK_PICKER_PLAN.md` | 233 lines · 2174 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/FK_PICKER_REQUIREMENTS.md` | 258 lines · 4196 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/_crp/FOCUS_FK_PICKER.md` | 10 lines · 69 words |

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

# CRP focus — FK pickers (generator-class)

Least-reviewed: this pair (new this session). Do not re-litigate onboarding archetype grammar or FR-FH-11 layout.

Weight:
1. Relation trigger vs `*Id` — polymorphic false positives (DueInstance.sourceId)
2. Options on all four form render paths (new/create-err/edit/update-err)
3. Tenant scoping + forged-id validation without changing shared `_coerce`
4. Drift dep-set / no new manifest (FR-10)
5. Accidental complexity: deleted pickers: section must stay deleted

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

### Optional second-pass suggestions (inside the appended appendix, still no triage)

If you still have budget under the max-suggestions cap after your first list, you may add a \`### Stress-test / adversarial pass\` subheading **inside your round block**, with **additional** numbered suggestions (continue **R{n}-S\*** / **R{n}-F\*** numbering within the same round — do not fabricate a separate round). Try to break your own prior conclusions where it genuinely helps; skip if redundant. **Still no in-chat list** — keep the chat reply to the short write-confirmation.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/FK_PICKER_PLAN.md`  ·  **Size:** 233 lines · 2174 words

```markdown
# FK Pickers on Generated Create/Edit Forms — Plan

**Pairs with:** `FK_PICKER_REQUIREMENTS.md` (v0.2)
**Version:** 0.2 (updated from the reflection pass that produced REQ §0)
**Date:** 2026-08-14
**Status:** authored, not implemented (no code written by this pass)
**Id convention:** FRs are `FR-1…FR-10` (det-req extraction); the `FR-FK-n` alias is for code comments
and cross-doc citation, matching `FORM_SUBMIT_BEHAVIOR`'s `FR-n` ↔ `FR-FS-n` in `htmx_generator.py`.

> **Shape of the work.** Not a widget change. One shared schema derivation (S1), one template
> rendering change (S3), one runtime helper threaded to **four** route call sites (S4), and two
> guards — existence validation and tenant scoping (S5/S6). Steps are ordered and acyclic: each
> depends only on earlier ones. S1 and S2 are strictly refactor-with-no-output-change, so they can
> land and be verified before any behavior moves.

---

## Step map (acyclic)

```
S0 characterization tests (byte-baseline)
 └─ S1 fk_targets() in prisma_parser        (FR-2)
     ├─ S2 re-express _fk_map on S1         (FR-2)   [no output change]
     └─ S3 picker predicate + <select> markup (FR-1/4/5/6/9/10)
         └─ S4 options helper + 4 route call sites (FR-3)
             ├─ S5 FK existence validation on submit  (FR-7)
             │   └─ S6 tenant scoping of options + check (FR-8)
             └─ S7 drift / byte-identity round-trip    (FR-10)
                 └─ S8 household pilot regen + lived smoke (O-4, closes P1-2)
```

No step depends on a later step. S5 depends on S4 because the existence check reuses the same
resolved target map the options helper emits; S6 depends on S5 because scoping is a predicate added
to both the query and the check introduced there.

---

## S0 — Characterization baseline (before any edit)

**Why first:** FR-2 and FR-10 both assert *byte-identical* output. That claim is unfalsifiable
without a recorded baseline, and the two refactor steps (S1/S2) are exactly where a silent
regression would hide.

| File | Change |
|------|--------|
| `tests/unit/backend_codegen/fixtures/` | Add a relation-bearing fixture schema (Chore→Member optional, Medication→Member required, Payment→Bill+Member, DueInstance with a bare `sourceId`) and a **no-relation** fixture. |
| `tests/unit/backend_codegen/test_fk_picker.py` (new) | Record the current `render_ui()` / `render_web()` output for the no-relation fixture as the byte-identity baseline; record current `sqlmodel-tables` output for the relation fixture. |

**Verifies:** the preconditions of FR-2 and FR-10.

---

## S1 — `fk_targets()` — the single FK-target resolver (FR-2)

| File | Change |
|------|--------|
| `src/startd8/languages/prisma_parser.py` | Add `fk_targets(schema, model_name) -> Dict[str, Tuple[str, str]]` mapping `fk_scalar → (target_model, ref_column)` by scanning each field's `@relation(fields:[…], references:[…])`. Move `_REL_FIELDS_RE` / `_REL_REFS_RE` here as the single home for the relation-attribute grammar. Skip composite FKs (len > 1) and list relations — both fall back to today's rendering per Non-goals. |

Chosen home rationale: this is pure schema derivation with no codegen concern, and both consumers
(`sqlmodel_renderer`, `htmx_generator`) already import from `prisma_parser` — so no new module and no
import cycle. Returns the **model** name (`f.type`), not the lowercased table name, because the
picker must query `select(Member)`; the table name is a rendering detail of one consumer.

**Verify:** unit — `fk_targets` on the relation fixture returns `{"assigneeId": ("Member","id"), …}`
and **omits** `DueInstance.sourceId`.

---

## S2 — Re-express `_fk_map` on `fk_targets` (FR-2) — no output change

| File | Change |
|------|--------|
| `src/startd8/backend_codegen/sqlmodel_renderer.py` | Replace the body of `_fk_map` (L144–171) with a thin adapter over `fk_targets`: `{fk: f"{model.lower()}.{ref}"}`. Delete the now-duplicate regexes. Keep the composite-FK zip behavior by having `fk_targets` expose the zipped pairs it already computes. |

**Verify:** S0's recorded `sqlmodel-tables` output for the relation fixture is byte-identical; the
existing `test_backend_codegen.py` / sqlmodel suites stay green.

---

## S3 — Picker predicate + `<select>` markup (FR-1, 4, 5, 6, 9, 10)

| File | Change |
|------|--------|
| `src/startd8/backend_codegen/htmx_generator.py` | (a) Add `is_fk_picker(schema, entity, field) -> bool` — true iff `field.name in fk_targets(schema, entity)`. **Do not** touch `_field_kind`: it feeds `_{e}_rules` and the shared `_coerce`/`_field_error` helpers, which must stay byte-identical (REQ §0, discovery 9). (b) In `_form_input_html` (L639–774), branch **before** the `kind == "select"` enum branch: emit a `<select>` whose `<option>`s iterate a context variable rather than being baked, reusing the enum branch's `selected` precedence shape (L716–734) for prefill → item → default. (c) Optional FK ⇒ leading blank `— none —` option; required ⇒ none (FR-5). (d) Empty-options ⇒ single disabled `— no <Target> yet —` option plus a link to `/ui/<target>/new` (FR-9). (e) Suppress the `_structural_hint` "copy from its detail page URL" line (L614) for picker fields — the instruction is now false. Label/hint/error stacking unchanged (FR-FH-11). |

Note (e) is a real behavioral coupling planning surfaced: the existing hint exists *because* the
field was a text box. Leaving it would tell a user to paste an id into a dropdown.

Labels are **not** resolved in the template — the route supplies `(value, label)` pairs (see S4), so
`form.html` gains no `display.yaml` dependency and its `htmx-form` dep-set is unchanged (FR-10).

**Verify:** unit on rendered template text — `assigneeId`/`memberId` are `<select>`;
`DueInstance.sourceId` is `<input type="text">`; the optional field has the blank option and the
required one does not; the no-relation fixture output matches the S0 baseline byte-for-byte.

---

## S4 — Options helper + all four route call sites (FR-3, 4)

| File | Change |
|------|--------|
| `src/startd8/backend_codegen/htmx_generator.py` | (a) Generate a per-entity `_options_<e>(session)` helper into `web.py` returning `{field: [(value, label), …]}` — one query per picker field: `select(Target)`, value = ref column, label = `_default_label_field(target)` value else the raw id (FR-4, reusing the existing `_LABEL_HEURISTIC`, L392–398). (b) Add `"options": _options_<e>(session)` to the context of **all four** `form.html` renders: `new_<e>` (L1129–1137), the `create_<e>` error re-render (L1157–1163), `edit_<e>` (L1189–1196), the `update_<e>` error re-render (L1205–1211). (c) `new_<e>` currently has **no session dependency** — add `session: Session = Depends(get_session)` to it. |

(c) is the one signature change planning found: three of the four sites already hold a session;
`new_<e>` does not, because until now the create form needed no data.

**Verify:** runtime (`tests/unit/backend_codegen/test_fk_picker_runtime.py`, following the
`test_*_runtime.py` convention) — a `TestClient` POST to `/ui/chore` that fails validation on
`anchorDate` returns a form whose `assigneeId` select still contains every Member option and
re-selects the submitted one. Assert on all four routes, not just `new`.

---

## S5 — FK existence validation on submit (FR-7)

| File | Change |
|------|--------|
| `src/startd8/backend_codegen/htmx_generator.py` | (a) Emit a per-entity `_{e}_fk = {"assigneeId": ("Member","id"), …}` map beside `_{e}_rules` / `_{e}_allowed` — **separate from `_{e}_allowed`**, whose generate-time-frozenset semantics stay unchanged. (b) After `_form_errors` returns and before `session.add`, in both `create_<e>` and `update_<e>`, check each non-empty picker value exists in its target; on miss add a field-level error and re-render the form (the same path a `_form_errors` failure takes, so S4's options are already in context). (c) Leave `_WEB_HELPERS` `_coerce` / `_field_error` untouched, and leave `validate_<e>` (L1140–1151) session-free (OQ-4). |

Placing the check after `_form_errors` rather than inside it is deliberate: `_form_errors` is a pure
function over the form dict in every generated app, and giving it a session would change a shared
helper's signature for all of them.

**Verify:** runtime — `POST /ui/chore` with `assigneeId=not-a-real-id` returns **200** with a
field-level error on `assigneeId` and **no** row written (assert the table count is unchanged), not
the 500 an `IntegrityError` produces today; a valid id still returns 303 with the
`FORM_SUBMIT_BEHAVIOR` `Location`/`?created=` contract intact.

---

## S6 — Tenant scoping of options and validation (FR-8)

| File | Change |
|------|--------|
| `src/startd8/backend_codegen/htmx_generator.py` | Thread the existing `owner_field` (already resolved per entity in `_entity_routes`, L1100–1117, and `render_web`'s `scoped` set, L1322–1324) into both (a) `_options_<e>`'s query — `.where(Target.<owner_field> == principal.id)` when the **target** is a scoped entity — and (b) S5's existence check. Add the `principal` dependency to `new_<e>` when any of its picker targets are scoped. A non-owned id reports the same "not a valid choice" field error as a nonexistent one (no existence disclosure), preserving the 404-not-403 posture. |

Scoping keys on whether the **target** entity is scoped, not the owning one — a scoped `Chore` may
point at an unscoped lookup table, and that must still populate.

**Verify:** runtime, two principals each owning one Member — principal A's `/ui/chore/new` lists
only A's Member; `POST /ui/chore` as A with B's member id returns a 200 form with a field-level error,
writes nothing, and the error text is identical to the nonexistent-id case.

---

## S7 — Drift and byte-identity round-trip (FR-10)

| File | Change |
|------|--------|
| `tests/unit/backend_codegen/test_fk_picker.py` | Assert no new manifest input: `htmx-form` stays in `drift._HUMAN_INPUTS_KINDS` with its 2-hash header; `fastapi-web` / `fastapi-web-forms` header hash counts unchanged; no `--picker*` flag added to `cli_generate.py`. |
| — | Round-trip: generate → `--check` clean; then verify the skip-hook (`owned_file_in_sync`) still reports in-sync for `htmx-form` and both `fastapi-web*` kinds — the FR-ED-16 breakage class, asserted rather than assumed. |

**Explicitly not changed** (the point of the step): `drift.py`, `assembler.py`, `cli_generate.py`,
`forms_manifest.py`, `display_manifest.py`. If any of these needs an edit, the design has drifted
back into the `pickers:`-manifest path the reflection pass rejected.

**Verify:** `startd8 generate backend --check` exits 0 immediately after a regenerate on the
relation fixture; the no-relation fixture output equals the S0 baseline byte-for-byte.

---

## S8 — Household pilot regen + lived smoke (O-4 — closes pilot P1-2)

| File | Change |
|------|--------|
| `~/Documents/dev/household/household-o11y` (consumer repo — regen only, no hand edits) | Regenerate with the same flags the pilot used (`--form-prose`, …) and re-run the pilot's smoke block. |

**Verify (lived):** `/ui/chore/new` shows an `Assignee` dropdown listing Member names — not a text
box asking for an id; selecting a member and saving returns 303 → detail; the pilot's existing
curl block (bad datetime → 200 with errors; good create → 303 `?created=`) still passes; and
`DueInstance`'s `sourceId` is still a text input. Then append the outcome to
`_PILOT_2026-08-14_onboarding-household.md`'s execution log and mark **P1-2** closed there.

---

## FR → step traceability

| FR | Steps |
|----|-------|
| FR-1 Relation-derived trigger | S1, S3 |
| FR-2 One shared resolver | S0, S1, S2 |
| FR-3 Options reach every render | S4 |
| FR-4 Zero-config labels | S3, S4 |
| FR-5 Optionality-correct blank | S3 |
| FR-6 Prefill precedence | S3, S4 |
| FR-7 Existence validation | S5 |
| FR-8 Tenant scoping | S6 |
| FR-9 Empty-target state | S3, S4 |
| FR-10 Presence-gated, dep-set-preserving | S0, S3, S7 |
| O-4 / pilot P1-2 | S8 |

Every FR has at least one step; every step serves at least one FR. No orphans in either direction.

---

## Removed from the v0.1 plan (by the reflection pass)

| v0.1 step | Why it is gone |
|-----------|----------------|
| "Write a relation parser for `@relation`" | `_fk_map` already does it — became S1/S2, a *promotion + de-duplication*, not new code. |
| "Add a `pickers:` section to `views.yaml` + `--pickers` flag + parse module" | Would change `form.html`'s drift dep-set and require threading through `drift.py` / `assembler.py` / `cli_generate.py` / the skip-hook (FR-ED-16 class). Schema-only derivation makes it unnecessary. Now asserted *absent* by S7. |
| "Teach `_field_kind` to return `fk`" | Would force an `"fk"` branch into the shared `_coerce` / `_field_error` helpers every generated app depends on. Replaced by a separate predicate (S3) + separate `_{e}_fk` map (S5). |
| "Add the FK's valid ids to `_{e}_allowed`" | Impossible: that set is fixed at generate time. Replaced by the runtime check in S5. |
| "Add a DB existence check to `/validate`" | Would give the blur endpoint a session for values the server itself produced. Deferred (OQ-4). |
| "Show the related record's label on list/detail too" | Separate change with its own query cost — moved to Non-goals. |

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/FK_PICKER_REQUIREMENTS.md`  ·  **Size:** 258 lines · 4196 words

```markdown
# FK Pickers on Generated Create/Edit Forms — Requirements

**Project:** startd8-sdk (python-contract-codegen)   **Criticality:** medium
**Version:** 0.2 (Post-planning — self-reflective update; pre-CRP)
**Date:** 2026-08-14
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Pairs with:** `FK_PICKER_PLAN.md`
**Inherits standards:** det-req-kit
**Audience:** end-user
**Trust boundary:** the browser form body is untrusted — an FK id arriving in a POST is a claim, not a fact; trust stops at `create_<e>` / `update_<e>`, where the id must be resolved against the DB and, when the app is tenant-scoped, against the principal's own rows before it is written.
**Data classification:** internal — generated app data; option *labels* are row content, so the options query inherits the app's row-visibility rules.

> **Companions** (cite, do not restate)
>
> - `_PILOT_2026-08-14_onboarding-household.md` — **P1-2** is the motivating defect ("FK fields are
>   raw text IDs (`assigneeId`, `memberId`, …); picker is later enhancement"); **P0-3 / P0-4** are the
>   unvalidated-write failure class this must not reopen.
> - `FORM_FIELD_LAYOUT_FR-FH-11.md` — the label → instruction → control → error stacking the picker obeys.
> - `FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md` — the PRG / `?created=` contract the picker must not disturb.
> - `EDITORS_ARCHETYPE_REQUIREMENTS.md` — the **promotion-door precedent** (an affordance becomes a
>   declared archetype only once proven), and its `FR-ED-16`, the manifest-derived drift/skip-hook trap
>   this requirement is deliberately shaped to avoid.
> - `ONBOARDING_ARCHETYPE_REQUIREMENTS.md` — the REQ whose non-goals deferred full FK picker widgets.
>   This document is that deferred item, not an extension of that archetype.
>
> **Id convention:** FRs are numbered `FR-1…FR-10` for det-req extraction; in code comments and
> cross-doc citation they carry the `FR-FK-n` alias, matching how `FORM_SUBMIT_BEHAVIOR`'s `FR-n`
> appear as `FR-FS-n` in `htmx_generator.py`.

---

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed this was a **widget change**: teach `_field_kind` to recognize `*Id` fields and emit a
> `<select>`. Planning against the real generator falsified that at three levels — the *trigger* is
> wrong (name suffix ≠ relation), the *options* cannot live in the template at all (enum options are
> baked at generate time; FK rows are runtime data, so four separate routes must supply them), and
> the *validation* path has no seam for a non-enumerable allowed-set. Planning also found the FK
> target resolver **already exists** and is authoritative, which removed the largest v0.1 work item.
> 10 corrections; scope moved from "one function" to "one resolver + four call sites + two guards",
> while the total *new machinery* went **down** (no new manifest, no new drift dep-set).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| A new relation resolver / parser extension is needed to map `assigneeId` → `Member`. | It already exists and is authoritative: `sqlmodel_renderer._fk_map()` (L144–171) parses `@relation(fields:[…], references:[…])`, and the generated `tables.py` already emits `foreign_key="member.id"`. It returns the *table* name (`f.type.lower()`), not the model class the picker must query. | Largest v0.1 item deleted. **FR-2** promotes one shared resolver returning the **model name** + ref column, and re-expresses `_fk_map` on it (single source, not a fork). |
| An FK field can be recognized by its `*Id` name suffix — `_structural_hint` (L614) already does exactly that. | The suffix is **wrong**. `DueInstance.sourceId` (household `schema.prisma` L196–208) is documented as *"a loose reference … (no ORM FK — polymorphic by sourceType)"*. A suffix-driven picker would render a select over a target that does not exist. | **FR-1** triggers on the `@relation` attribute only. `sourceId` staying a text input is a named **Verify**, not an accident. |
| Adding `<select>` to `form.html` is the whole rendering change (enums do it that way). | Enum options are **baked into the template at generate time** (L709–742). FK options are **runtime rows** and cannot be. The template must iterate a context variable, and **every** route rendering `form.html` must supply it: `new_<e>` (L1129), the `create_<e>` error re-render (L1160), `edit_<e>` (L1189), the `update_<e>` error re-render (L1208). | Biggest scope correction. **FR-3** requires **one** options helper called by all **four** sites; a missed site is a silently-empty picker on the error path — a context-arrival failure. |
| `_{e}_allowed` can carry the valid FK ids, the way it carries enum values. | `_{e}_allowed` is a **generate-time frozenset** (L1088–1092); an FK's valid set is unknowable at generate time. Today a forged `assigneeId` passes `_form_errors` untouched and dies as an `IntegrityError` → 500 — the same class as pilot **P0-3 / P0-4**. | **FR-7** adds a **runtime existence check** via a separate generated `_{e}_fk` map; `_{e}_allowed` semantics are unchanged. |
| Reading options is a read of already-visible data, so tenancy is unaffected. | False, and it is a **new** leak. Every DB-touching handler is owner-scoped (`owner_field == principal.id`, L1100–1117, FR-TEN-2). A naive `select(Member)` for options would put **other tenants' row labels and ids** in the dropdown — a surface that previously exposed neither. | **FR-8** scopes the options query *and* the existence check with the same `owner_field`, preserving the 404-not-403 posture (never leak existence). |
| The option label needs a new `pickers:` manifest to say which column to show. | It needs no config at all: `_default_label_field` + `_LABEL_HEURISTIC = ("name","title","label","headline")` (L392–398) already exist for the row view-link, and are already the zero-config answer to "what does a row read as". | **FR-4** reuses the heuristic. The `display.yaml` `label_field` **override** is deferred to a Non-goal with a grounded reason: it would add a display hash to `web.py`, which today has none. |
| A `pickers:` manifest is the natural way to make this opt-in. | It would be the expensive way. `htmx-form` sits in `drift._HUMAN_INPUTS_KINDS` (L101) as a schema+human_inputs 2-hash kind; a new input changes its dep-set and must be threaded through `owned_file_in_sync` / `check_drift` / `assembler` / `cli_generate` / the skip-hook — exactly the breakage `FR-ED-16` records. | **FR-10**: derive from the schema alone. **No new manifest, no new CLI flag, no new drift dep-set.** Machinery went down, not up. |
| Pre-selecting a parent from a link (`?assigneeId=…`) is a new requirement. | Already wired: `new_<e>` prefills any query param whose key is in `_{e}_rules` (L1131–1133). | **FR-6** narrows to "honor the existing prefill precedence" (prefill → current item → default), reusing the enum select's precedence expression (L716–734). No new mechanism. |
| The widget kind and the coercion kind are the same thing, so `_field_kind` should return `"fk"`. | They diverge here for the first time. `_field_kind` feeds **both** the template widget *and* `_{e}_rules`, which drives the shared `_coerce` / `_field_error` helpers in `_WEB_HELPERS` — helpers every generated app already depends on. Returning `"fk"` would force a branch into both. | **FR-1 / FR-7**: a separate `is_fk_picker()` predicate decides the widget; `_{e}_rules` keeps `("text", …)` byte-identical and FK-ness rides the separate `_{e}_fk` map. Shared helpers unchanged ⇒ no cross-app regression surface. |
| Blur-time `/validate` should check that the id exists. | `validate_<e>` (L1140–1151) takes **no session dependency** — adding one to reach the DB widens a hot, per-blur endpoint for a control whose values the server itself just produced. | **FR-7** narrows existence checking to submit (create/update, which already hold a session). Blur validation covers required-ness only; recorded as a resolved open question. |
| A required FK always has something to point at. | Nothing guarantees the target table is non-empty. A required FK with zero rows renders an **unfillable** form — strictly worse than today's text box, where a user could at least paste an id. | **FR-9** (new requirement, absent from v0.1) specifies the deterministic empty state: a disabled `— no <Target> yet —` option plus a link to `/ui/<target>/new`. |

**Resolved open questions:**
- **OQ-1 → Trigger on `@relation`, never on the name.** `DueInstance.sourceId` is the live
  counter-example; the schema already carries the authoritative answer.
- **OQ-2 → Options are route-supplied, not template-baked.** Enum parity is impossible; the four
  form-rendering call sites are the real surface area.
- **OQ-3 → No manifest in v1.** Schema plus the existing label heuristic fully determine the picker,
  so the drift dep-sets of `form.html` and `web.py` are unchanged.
- **OQ-4 → Existence validation at submit only.** Blur `/validate` stays session-free.
- **OQ-5 → Label override is deferred, not designed-out.** `display.yaml` `label_field` is the right
  eventual home; it costs `web.py` a new hash, so it waits for a second consumer to ask.

### 0.1 Lessons-Learned Hardening

> Consulted the ingested corpus and the pattern catalog with the routed decision-class keys
> (`#7 audience/presentation`, `#13 interactive-surface/rendering`), plus `det-req-kit/BACKEND_ROUTING.md`.
> Honest result: **thin.**

- **`contextcore lesson recall --project lessons-craft --task-type "interactive-surface/rendering"`**
  — ran; returned 6 hits, all at the flat 0.70 baseline and all off-domain (Supabase edge function,
  frontend test seam, Shopify migration). **No applicable lesson**; nothing applied, nothing recorded
  via `record-application`.
- **`python -m contextcore.learning.pattern_catalog recall "code × interactive-surface/rendering"
  "requirement × audience/presentation"`** — ran; returned `(none — browse fallback)`.
- **Markdown browse fallback (`PATTERN-CATALOG.md`)** — nearest-key entry is **PC-10 Deterministic
  Surface = Node Navigator** (`code × interactive-surface/rendering`). Only its "never a second loop"
  clause is in scope at this size, and it **was** applied: the picker rides the one existing
  select/validate path instead of introducing a parallel widget pipeline (FR-1, FR-7). The rest of
  PC-10 (node grammar, manifest recognizer, turn-loop) is **deliberately not** applied — imposing a
  navigator archetype on a single form control is the over-application this corpus warns about. Not
  cited via `pattern_catalog cite`, because reusing one clause of a K2 pattern is not the reuse the
  cite counter measures.
- **Backend re-check (`BACKEND_ROUTING.md`)** — re-ran the signal table after planning. FRs touch
  **entity / page / view** codegen only: no console script, no `--flag`, no store / migration /
  `app/db.py` seam (planning specifically *removed* the CLI-flag option, OQ-3). So
  `startd8-python-cascade` is **confirmed, not defaulted**, and no dual backend applies. The routing
  table's **security** row fired (untrusted input) → header `Trust boundary` plus two `security` risks
  and boundary-exercising Verifies on FR-7 / FR-8. Its **UX** row fired (audience) → header
  `Audience: end-user` plus user-observable Verifies on FR-4 / FR-9.

### 0.2 Design-Principle Hardening

> Checked the draft against `PRINCIPLE-INDEX.md` §2 filtered on the same keys. Five principles
> changed the draft; every change **removed** machinery rather than adding it.

- **[Genchi Genbutsu]** (`× fail-loud/validation-gate`, `× single-source/no-drift`) — forced the
  question "does the trigger bind to the authoritative artifact or to an inferred proxy?" The `*Id`
  suffix is a proxy; `@relation` is the artifact. Grounding whole-tree against the real household
  schema produced the `DueInstance.sourceId` counter-example → **FR-1** binds to `@relation` and its
  negative case is a Verify.
- **[Mottainai]** (`× idempotency/reuse`) — forced "is a later stage re-deriving what an earlier one
  already produced?" It was: v0.1 planned a second FK parser beside `_fk_map` and a second label
  policy beside `_default_label_field`. → **FR-2** makes one resolver the single source (with
  `_fk_map` re-expressed on it, not forked); **FR-4** reuses the existing label heuristic.
- **[Accidental-Complexity]** (META) — forced "is this adding a layer to compensate for something one
  general rule dissolves?" Two layers were removed before being built: the `pickers:` manifest (with
  its drift dep-set, CLI flag, and `FR-ED-16`-class skip-hook threading) and an `"fk"` branch inside
  the shared `_coerce` / `_field_error` helpers. → **FR-10** (schema-only, no new input) and the
  separate `_{e}_fk` map that leaves the shared helpers byte-identical.
- **[Context-Correctness-by-Construction]** (`× context-arrival/data-wiring`) — forced "can the
  required context silently arrive as `None`?" It can, and would have: options reaching `new_<e>` and
  `edit_<e>` but not the two error re-renders is precisely "slot exists, artifact never arrives", and
  it would only be visible *after* a validation failure. → **FR-3** names all four call sites,
  requires one helper, and makes the error path its Verify.
- **[Sotto]** (`× audience/presentation`, advisory) — the presence-gated, byte-identical-when-absent
  seam. → **FR-10** requires byte-identical output for a schema with no relation FK.

---

## Overview

Generated create/edit forms currently render foreign-key fields as raw text inputs, so an end user
must open a second tab, find the related record, and copy a CUID out of its URL to fill in
`assigneeId`. This adds a deterministic **relation picker**: any scalar field that a Prisma
`@relation(fields: […])` names as its FK renders as a populated `<select>` of the target entity's
rows, labelled by the target's existing zero-config label field, with server-side scoped validation
on submit. It is derived entirely from the schema the generator already parses — no new manifest, no
CLI flag, no autocomplete library, no per-app hand-written widget, `$0` LLM. Deliberately later:
typeahead, relation browsing, inline creation of the related record, and any `display.yaml`-driven
label override.

## Objectives

- O-1: A relation FK renders as a populated `<select>` on generated create and edit forms, with zero hand-written per-app widget code and `$0` LLM spend.
- O-2: No forged, stale, or cross-tenant FK id can be written through the HTMX surface, and no picker discloses a row the principal could not already read.
- O-3: Net new machinery is zero — no new manifest, no new CLI flag, no change to any owned kind's drift dep-set; an app with no relation FK regenerates byte-identically.
- O-4: Pilot P1-2 closes — a household user can complete a Chore create form without leaving the page to look up an id.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| security | A forged or stale FK id in the POST body is written unchecked; today it surfaces as an `IntegrityError` 500 or a dangling reference (pilot P0-3 / P0-4 class). | Scoped runtime existence check on create/update before commit; field-level error on miss (FR-7). | high |
| security | An unscoped options query puts another tenant's row labels and ids in the dropdown — a read-side leak on a surface that previously showed neither. | Options query and existence check reuse the same `owner_field` scoping as every other handler (FR-8); 404-not-403 posture preserved. | high |
| quality | Options supplied to some but not all four form-rendering routes, so the picker renders empty exactly on the validation-error re-render — the path users hit most. | One shared options helper, all four call sites named; the error path is the Verify (FR-3). | high |
| quality | A name-suffix trigger renders a picker for a polymorphic id with no target (`DueInstance.sourceId`). | Trigger on `@relation` only; the negative case is a named Verify (FR-1). | high |
| quality | A required FK whose target table is empty produces an unfillable form — worse than the text input it replaced. | Deterministic empty state: disabled option plus a link to create the target (FR-9). | medium |
| cost | A new manifest input would change `form.html`'s drift dep-set and require threading through five files plus the skip-hook (`FR-ED-16` class breakage). | Schema-only derivation; label override deferred to a Non-goal (FR-10). | medium |
| quality | Scope creep: "picker" drifts into typeahead, relation browsing, or inline creation of the related record. | Non-goals, enumerated with rationale. | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Relation-derived picker trigger.** A writable scalar field renders as a `<select>` if and only if some `@relation(fields: […])` on its model names it as an FK, so the `*Id` name suffix never triggers a picker. Touches: Chore, Medication, Payment, DueInstance, <entity>/form.html. Verify: given the household schema, `Chore.assigneeId` and `Medication.memberId` render `<select name="assigneeId">` and `<select name="memberId">`, while `DueInstance.sourceId` — a documented polymorphic reference with no `@relation` — still renders `<input type="text">`. Serves: O-1
- **FR-2 — One shared FK-target resolver.** A single helper maps each FK scalar to its `(target_model, ref_column)` from `@relation`, and `sqlmodel_renderer._fk_map` is re-expressed on top of it rather than kept as a second parser. Touches: Chore, Member, <entity>/form.html, app/web.py. Verify: given the household schema, the resolver returns `assigneeId → ("Member","id")`, and the existing `sqlmodel-tables` output is byte-identical before and after the re-expression (`--check` clean, no regenerated diff). Serves: O-3
- **FR-3 — Options reach every form render.** One generated per-entity options helper supplies value/label pairs for each picker field and is called by all four routes that render `form.html`: `new_<e>`, the `create_<e>` validation-error re-render, `edit_<e>`, and the `update_<e>` validation-error re-render. Touches: app/web.py, <entity>/form.html. Verify: given a POST to `/ui/chore` that fails validation on a different field, the returned form's `assigneeId` select still lists every eligible Member rather than being empty, and re-selects the submitted value. Serves: O-1
- **FR-4 — Zero-config option labels.** Each option's value is the target's referenced column and its label is the target's existing zero-config label field (`name` / `title` / `label` / `headline`), falling back to the raw id when the target has none. Touches: Member, <entity>/form.html. Verify: given a Member named "Sam", the Chore form's `assigneeId` option reads `Sam` with `value="<Sam's id>"`; given a target with no label-heuristic column, the option text is the id and the form still submits. Serves: O-1
- **FR-5 — Optionality-correct blank option.** An optional FK gets a leading blank `— none —` option and a required FK gets none. Touches: Chore, Medication, <entity>/form.html. Verify: given the household schema, `Chore.assigneeId` (`String?`) offers a blank option that submits as unset while `Medication.memberId` (required) offers none, and submitting the Chore form with the blank chosen stores a null `assigneeId` and returns 303. Serves: O-1
- **FR-6 — Existing prefill precedence honored.** The picker's selected option follows the same precedence the enum select already uses: submitted or prefilled value, else the current record's value, else the blank option (optional) or first option (required). Touches: app/web.py, <entity>/form.html. Verify: given `GET /ui/chore/new?assigneeId=<member-id>` that Member's option carries `selected`, and given `GET /ui/chore/<id>/edit` on an already-assigned Chore the assigned Member's option carries `selected`. Serves: O-1
- **FR-7 — Server-side FK existence validation on submit.** Create and update validate every picker field against the target's rows before commit via a separate generated FK map, returning a field-level error on miss, while the shared `_coerce` / `_field_error` helpers and the `_{e}_rules` kinds stay unchanged and blur `/validate` remains session-free (required-ness only). Touches: app/web.py, Chore, Medication. Verify: given `POST /ui/chore` with `assigneeId=not-a-real-id` the response is a 200 form carrying a field-level error on `assigneeId` with no row written — not a 500 — and given a valid id the response is a 303 as today. Serves: O-2
- **FR-8 — Tenant-scoped options and validation.** In a tenant-scoped app both the options query and the existence check filter the target by the same `owner_field == principal.id` predicate the other handlers use, and a non-owned id is reported as an invalid choice rather than as a distinguishable "exists but forbidden". Touches: app/web.py, Member. Verify: given two principals each owning one Member, principal A's Chore form lists only A's Member, and a `POST /ui/chore` from A carrying B's member id returns a 200 form with a field-level error identical to the nonexistent-id case and writes nothing. Serves: O-2
- **FR-9 — Empty-target empty state.** When a picker's target has no eligible rows the select renders a single disabled `— no <Target> yet —` option plus a link to that target's create page, and a required picker in that state cannot be satisfied by a forged id. Touches: <entity>/form.html, app/web.py, Member. Verify: given zero Members, the Chore create form shows a disabled `— no Member yet —` option and a working link to `/ui/member/new`, and posting a fabricated `assigneeId` in that state returns the form with a field-level error. Serves: O-4
- **FR-10 — Presence-gated and dep-set-preserving.** The picker derives from the Prisma schema alone: no new manifest, no new CLI flag, and no change to the drift dep-set or header hash count of `htmx-form`, `fastapi-web`, or `fastapi-web-forms`; a schema with no relation FK regenerates byte-identically. Touches: <entity>/form.html, app/web.py, DueInstance. Verify: given a schema with no `@relation`, `startd8 generate backend` output is byte-identical to the pre-change output; given the household schema, `startd8 generate backend --check` is clean immediately after a regenerate and no `--picker` flag exists. Serves: O-3

## Non-goals

- No autocomplete or typeahead vendor library — no Select2 / Choices.js / Tom Select / combobox dependency, and no client-side search over options. A plain `<select>` only.
- No relation or graph browser — no popup to explore the target entity, and no nested related-record navigation from the form.
- No confirm-walk — the picker introduces no multi-step confirm sequence; the existing PRG + `?created=` contract (`FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md`) is unchanged.
- Not the onboarding archetype — this is the item the onboarding REQ's non-goals deferred, not an extension of `onboarding:`; no `/welcome`, tips, or checklist surface is touched.
- Not the `editors:` bulk surface — no bulk child-field editing and no picker inside `editor-form` templates in v1; `EDITORS_ARCHETYPE_REQUIREMENTS.md` is cited as promotion-door precedent only.
- Not the import path — `import_codegen` / `import_surface` FK resolution is untouched (`GENERATED_IMPORT_PATH_REQUIREMENTS.md` owns it).
- No inline creation of the related record — no "add new Member" modal from the Chore form; the empty state links to the existing create page instead (FR-9).
- No `display.yaml` `label_field` override for option labels — deferred, not designed-out. `web.py` has no `display.yaml` dependency today; honoring the override there would add a hash to `fastapi-web` / `fastapi-web-forms` and require threading `display_text` through `owned_file_in_sync` / `check_drift` / `assembler` / the skip-hook. It waits for a second consumer.
- No FK label denormalization on list or detail — `list.html` / `detail.html` keep showing the raw id; making them read the target's label is a separate change with its own query cost.
- No composite multi-column FK pickers and no list or many-to-many relations — a composite `@relation` and a `Member[]`-style relation both fall back to today's rendering.
- No blur-time existence validation — `/validate` stays session-free (OQ-4).

## Owned fields

Only humans enter: none

No new owned field is introduced. The picker changes *how* an existing FK column is entered, not who
may write it; the `human_inputs.yaml` owned-field policy is unchanged and continues to drop owned
columns from every write surface before a picker is ever considered.

## Contract projection

- **Backend:** startd8-python-cascade
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8 (cascade vocabulary: `entity` · `page` ·
  `view` · `completeness` · `ai-assist`) → `KICKOFF_AUTHORING_CONTRACT.md` §2.x. Generator seam (cite,
  do not restate): `src/startd8/backend_codegen/htmx_generator.py`,
  `src/startd8/backend_codegen/sqlmodel_renderer.py`.

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| Chore | entity | structure | Optional FK `assigneeId String?` → Member; the pilot P1-2 surface |
| Medication | entity | structure | Required FK `memberId` → Member; the no-blank-option case |
| Payment | entity | structure | Two FKs on one form (`billId` required, `memberId?` optional) |
| Member | entity | structure | Picker target; label from the existing `name` heuristic |
| DueInstance | entity | structure | Negative case: `sourceId` is polymorphic with no `@relation`, so it stays a text input |
| <entity>/form.html | view | structure | Owned kind `htmx-form`; select widget, blank option, empty state |
| app/web.py | view | structure | Kinds `fastapi-web` / `fastapi-web-forms`; options helper, four call sites, FK existence check, tenant scoping |
| <entity>/list.html | view | structure | Unchanged — FK label denormalization is a Non-goal |

---

*v0.2 — Post-planning self-reflective update. 10 assumptions corrected: 3 requirements narrowed
(FR-2, FR-4, FR-6 — existing machinery already met them), 1 added (FR-9, the empty-target state),
2 deferred to Non-goals (`display.yaml` label override, blur-time existence validation), 1 reframed
at the correct layer (options are route-supplied, not template-baked — FR-3), and 2 mechanisms
deleted before they were built (the `pickers:` manifest, an `"fk"` branch in the shared coercion
helpers). 5 open questions resolved. Lessons recall and pattern recall were run and recorded as thin
in §0.1; 5 design principles applied in §0.2. Ready for CRP-lite (S-size: one Appendix-C round plus
A/B triage, per `BACKEND_ROUTING.md`).*

## Appendix A — Accepted (with where merged)

## Appendix B — Rejected (with rationale)

## Appendix C — Incoming review rounds

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
