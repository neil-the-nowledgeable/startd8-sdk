# Convergent Review Prompt

**Generated:** 2026-06-01 21:23:54 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md` | 198 lines · 1489 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md` | 254 lines · 2365 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/.approach_a_crp_focus.md` | 32 lines · 248 words |

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

# Where review input matters most — Approach A (Project-Knowledge Artifact)

Weight the review toward these five concerns:

1. **FR-2 CodeGraph-convergence schema (R4).** Is the `ProjectKnowledge` pydantic
   shape (models / module_paths / invalid_module_paths / packages / tsconfig /
   file_exports) the right contract for a future Mieruka `CodeGraph` producer to
   return — or does it bake in SDK-only assumptions that would force a rewrite? This
   is the load-bearing "converge on schema, not implementation" decision.

2. **S5 refactor risk.** Subsuming the shipped Mode-A/Mode-B inheritance + the
   heuristic-gated FR-3 Prisma injection into one artifact-sourced path. Is "keep the
   existing Mode-A/B tests green" a sufficient gate, or are there behaviors
   (`_collect_upstream_interfaces` edge cases, absent-anchor warnings, Mode-A
   not-yet-generated producers) that the refactor could silently change?

3. **OQ-4 adherence (R1).** Will a P0 section + explicit negatives + "use only these
   fields" actually move the LLM off its canonical-name prior, or is injection
   necessary-but-insufficient? Is the FR-8 reproduction harness a strong enough
   measurement, and what's the escalation if adherence measures weak?

4. **OQ-2 relevance scoping.** The whole-schema-when-≤12-models fallback vs
   import-closure scoping — token cost vs completeness. Is the entity-name match
   (target_files + description) robust, or will it miss entities a feature touches
   transitively?

5. **FR-4 negatives.** Seeding the recurring inventions (`@/lib/prisma`,
   `@/lib/db/<model>`, `@/lib/ai/client`) — is a hard-seeded negative list the right
   mechanism, or does it need to be derived to generalize beyond strtd8?

Also flag any FR without a testable acceptance criterion, and any plan step (S1–S7)
that is not traceable to an FR.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md`  ·  **Size:** 198 lines · 1489 words

```markdown
# Approach A — Project-Knowledge Artifact — Implementation Plan

**Version:** 1.0 (pairs with `APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md` v0.2)
**Date:** 2026-06-01
**Status:** Draft for CRP — resolves OQ-2/4/5/6/7; maps FR-1…FR-10 to live seams.

This plan decomposes Approach A into discrete, testable changes against the **existing**
seams (the requirements' §0 established that this is a *generalization* of shipped code,
not a greenfield build). It resolves the open questions, fixes the data model, and
sequences the work so each step ships green.

---

## 1. Architecture decisions (resolves the open questions)

| OQ | Decision | Rationale |
|----|----------|-----------|
| **OQ-1** (schema vs impl) | Define `ProjectKnowledge` (pydantic) + a `ProjectKnowledgeProducer` Protocol; ship a `RegexProjectKnowledgeProducer` now behind it | Converge on the **contract**; the Mieruka `CodeGraph` becomes a drop-in producer later without touching the injection seam. Doesn't block on pin-conflicted tree-sitter Phase 1. |
| **OQ-2** (relevance scope) | **Module-path table: always injected in full** (it's tiny — a handful of modules). **Prisma field sets: entities the feature references** (names found in `target_files` paths + the feature description/plan slice), with a **whole-schema fallback when the model count ≤ `PK_FULL_SCHEMA_MAX_MODELS` (default 12)** | strtd8 has 9 models — full-schema injection is cheap and eliminates "the heuristic skipped my entity" (the Gap-A cause). Larger projects scope down. |
| **OQ-4** (adherence) | v1 maximizes odds (P0 section, authoritative framing, explicit negatives, a one-line draft instruction) and **measures** via the FR-8 re-run. If adherence is weak, escalate (draft self-check / Approach C) — tracked, not built now | The postmortem's own caveat: Approach A can't *force* consultation. Measure before adding machinery. |
| **OQ-5** (tree-sitter vs regex) | **Regex/stdlib for v1** — reuse `extract_ts_exports` + `prisma_parser` | tree-sitter export-fidelity gain doesn't justify the pin-conflict isolation cost in v1; the producer is swappable (OQ-1) so tree-sitter can back it later. |
| **OQ-6** (persistence) | **Rebuild once per batch**, persist `forward_project_knowledge.json` to the run output dir for audit; no mtime cache | Always-fresh, deterministic (NFR-1), trivial. Caching is premature at batch cadence. |
| **OQ-7** (negatives) | **Seed** the recurring inventions (`@/lib/prisma`, `@/lib/db/<model>`, `@/lib/ai/client`); derive from canonical-name priors later | Cheap, covers the observed recurrences now; extensible as new inventions surface. |

---

## 2. Data model — the shared schema (FR-1, FR-2)

New module `src/startd8/contractors/project_knowledge.py`:

```python
class FieldInfo(BaseModel):
    type: str
    nullable: bool = False
    default: str | None = None
    is_id: bool = False
    unique: bool = False

class ModelInfo(BaseModel):
    fields: dict[str, FieldInfo]
    relations: list[dict]          # {name, model, many}

class ModulePath(BaseModel):
    specifier: str                 # "@/lib/db"
    exports: list[str]             # ["db"]

class ProjectKnowledge(BaseModel):
    models: dict[str, ModelInfo] = {}          # Prisma
    module_paths: dict[str, ModulePath] = {}   # symbol/module -> path+exports
    invalid_module_paths: list[str] = []       # FR-4 negatives
    packages: list[str] = []                   # package.json deps+devDeps
    tsconfig: dict = {}                         # paths + target/lib/strict/module
    file_exports: dict[str, list[str]] = {}    # path -> exported symbols
    schema_version: int = 1

class ProjectKnowledgeProducer(Protocol):
    def build(self, project_root: str, anchors: list[str]) -> ProjectKnowledge: ...
```

`RegexProjectKnowledgeProducer.build()` composes the **already-shipped** extractors
(FR-6): `prisma_parser.parse_prisma_schema` → `models`; `extract_ts_exports` over
project TS files → `file_exports` + `module_paths`; `cross_file_imports._package_name`
+ a `package.json` read → `packages`; a `tsconfig.json` read → `tsconfig` (+ `paths`
feed `module_paths`). `invalid_module_paths` seeded from a constant list (OQ-7).

The pydantic model **is** the CodeGraph view contract (FR-2): a future
`CodeGraphProjectKnowledgeProducer` returns the same type.

---

## 3. Renderer — artifact → P0 spec section (FR-4, FR-5)

`render_project_knowledge(pk: ProjectKnowledge, *, entities: list[str]) -> str` emits a
compact authoritative block:

```
## Project contract (authoritative — use ONLY what is listed)
Imports: the Prisma client is `import { db } from "@/lib/db"`. AI service:
`import { ... } from "@/lib/ai/service"`. Do NOT import `@/lib/prisma`,
`@/lib/db/<model>`, or `@/lib/ai/client` — they do not exist.
Prisma models (use only these fields; do not invent fields):
- Capability: id, ownerId, source, confirmed, name?, category?, description?, proficiency?, notes?
- Outcome: id, ownerId, ... ; Metric has NO foreign key to Outcome.
Dependencies available (package.json): @anthropic-ai/sdk, zod, next, ...
```

Negatives (FR-4) and the "use only these fields" instruction (FR-5) are explicit. The
renderer is the single place that frames the truth authoritatively.

---

## 4. Injection seam refactor (FR-3, FR-6, FR-9, FR-10)

`prime_contractor.py`:

1. **Build once per batch.** In `load_seed_context` (where `project_root` +
   `seed_upstream_anchors` are known), construct `self._project_knowledge =
   self._pk_producer.build(self.project_root, self.seed_upstream_anchors)` and persist
   it to `<run>/plan-ingestion/forward_project_knowledge.json`. `self._pk_producer`
   defaults to `RegexProjectKnowledgeProducer()` (swappable — OQ-1).
2. **Refactor `_collect_upstream_interfaces`** to source its renders from the artifact:
   - Mode A/B TS interface rendering → `file_exports` / `module_paths` lookups (FR-6;
     preserve existing output so `test_upstream_interface` / `test_mode_b_prisma_inheritance`
     stay green).
   - **Replace** the heuristic-gated FR-3 Prisma block: always append
     `render_project_knowledge(pk, entities=relevant_entities(feature, pk))` (FR-3) —
     no `_feature_mirrors_data_model` gate.
3. **Relevance scope** `relevant_entities(feature, pk)` (OQ-2): entity names matched in
   `feature.target_files` + `feature.description`; if `len(pk.models) <=
   PK_FULL_SCHEMA_MAX_MODELS`, return all models.
4. **Token bound + logging** (FR-9): log artifact size + the rendered section's token
   estimate per feature; warn if over `PK_SECTION_TOKEN_BUDGET` (default ~800).
5. **Read-only** (FR-10): the artifact is built before per-feature generation and not
   mutated; Mode-A producer outputs already surface via the existing on-disk reads
   (keep that path; the artifact augments, doesn't replace, sibling inheritance).

---

## 5. Implementation sequence (each step ships green)

| Step | Change | FRs | Files | Test |
|------|--------|-----|-------|------|
| **S1** | `ProjectKnowledge` schema + `ProjectKnowledgeProducer` protocol | FR-1, FR-2 | `contractors/project_knowledge.py` | schema round-trip + protocol |
| **S2** | `RegexProjectKnowledgeProducer.build()` reusing shipped extractors | FR-1, FR-6, FR-7 | same + reuse `upstream_interface`, `prisma_parser`, `cross_file_imports` | build against strtd8 root → asserts `Capability` fields, `db→@/lib/db` |
| **S3** | `render_project_knowledge()` with negatives + field-set authority | FR-4, FR-5 | same | golden render asserts negatives + exact fields |
| **S4** | Build-once-per-batch + persist json | FR-1, FR-9, NFR-1/3 | `prime_contractor.load_seed_context` | artifact written; partial on missing schema/tsconfig |
| **S5** | Refactor `_collect_upstream_interfaces` to source from artifact; drop heuristic gate | FR-3, FR-6, FR-10 | `prime_contractor._collect_upstream_interfaces` | existing Mode-A/B tests green + new always-injected test |
| **S6** | Relevance scope + token bound/logging | FR-3, FR-9 | same | scoping unit + budget log assertion |
| **S7** | Run-011 reproduction harness | FR-8 | `tests/.../test_approach_a_repro.py` | PI-001/002/004/007 fixtures: no invented fields/paths |

S1–S3 are pure additions (no behavior change). S5 is the only behavior-changing step —
gated by keeping the existing Mode-A/B tests green.

---

## 6. Testing strategy (FR-8 is the headline gate)

- **Unit:** schema round-trip; producer against a fixture project (the strtd8 schema +
  a `lib/db.ts` + `package.json` + `tsconfig.json` fixture); renderer golden output.
- **Regression:** `test_upstream_interface.py`, `test_mode_b_prisma_inheritance.py`,
  `test_cross_file_integrity_postmortem.py` stay green (FR-6 preserves behavior).
- **Reproduction (FR-8):** fixtures derived from the run-011 failed features. With the
  artifact injected, assert the spec context contains the real `Capability`/`Outcome`/
  `Metric`/`Differentiator` field sets and the `@/lib/db` / `@/lib/ai/service` paths,
  and that the negatives for `@/lib/prisma` etc. are present. A no-artifact baseline
  asserts the prior (gappy) context — proving the artifact is what changes the outcome.
- **End-to-end (optional, post-merge):** a real `--fresh` M4 re-run; expect the Gap-A/B
  failure classes at zero and the verdict to rise from 0.50 toward 1.00 (OQ-4 evidence).

---

## 7. Risks

- **R1 — Adherence (OQ-4).** The LLM may still ignore the P0 truth. *Mitigation:* explicit
  negatives + "use only these fields" instruction; measure via FR-8/E2E; escalate to a
  draft self-check only if measured weak. **This is the load-bearing uncertainty.**
- **R2 — Token cost.** Whole-schema injection on a large project. *Mitigation:* FR-9
  bound + `PK_FULL_SCHEMA_MAX_MODELS` scope-down + logging.
- **R3 — Refactor regression (S5).** Subsuming Mode-A/B could change their output.
  *Mitigation:* the existing Mode-A/B tests are the gate; S5 lands only when they pass.
- **R4 — Schema drift from CodeGraph (FR-2).** The v1 schema might not match Mieruka's
  eventual `CodeGraph` query shape. *Mitigation:* keep the schema minimal + documented;
  this is exactly what the CRP should pressure-test (it's the convergence decision).
- **R5 — Regex extractor fidelity (OQ-5).** `extract_ts_exports` may miss exotic export
  forms. *Mitigation:* v1 targets the Next.js/Prisma surface that actually failed;
  tree-sitter backend is the upgrade path.

---

## 8. What this plan deliberately leaves out

Per the requirements' Non-Requirements: no full CodeGraph build, no SCIP tier, no
Approach B retirement, no Approach D, no `clean-prior-run` changes. The verification-
ledger consolidation (RUN-011 Gap D / Fix 3) is independent and can ship in any order.

---

*Plan 1.0 — pairs with REQUIREMENTS v0.2. Resolves OQ-1/2/5/6/7; OQ-4 (adherence) is a
measured uncertainty carried into validation (R1). Recommended next: dual-document CRP
(`/new-cnvrg-rvw-prmpt`) over both docs — the FR-2 CodeGraph-convergence schema and the
S5 refactor are the two items most worth external review — then implement S1→S7.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**;
> dispositions recorded in **Appendix A** (applied) / **Appendix B** (rejected).
> Scan A/B/C first; do not re-propose settled or rejected items.

### Appendix A: Applied Suggestions
_None yet._

### Appendix B: Rejected Suggestions (with Rationale)
_None yet._

### Appendix C: Incoming Suggestions (Untriaged, append-only)
_Awaiting first review round._
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/APPROACH_A_PROJECT_KNOWLEDGE_REQUIREMENTS.md`  ·  **Size:** 254 lines · 2365 words

```markdown
# Approach A — Pre-flight Project-Knowledge Artifact (the CodeGraph slice)

**Version:** 0.2 (Post-planning — self-reflective update; grounded in the live seams)
**Date:** 2026-06-01
**Status:** Draft for review — pairs with a forthcoming `APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md`
**Source incidents:** `RUN_011_M4_FIELD_AND_PATH_INVENTION_POSTMORTEM.md` (Gaps A+B),
`CROSS_FILE_CONTRACT_RESOLUTION.md` §5 (Approach A) + §11 (the CodeGraph convergence).

> **What this is.** A deterministic, read-only **project-knowledge artifact** built
> before generation and injected as a P0 spec-context section, carrying the
> authoritative answers the LLM keeps inventing: the exact Prisma field sets, the
> canonical module-import paths (and the *non-existent* ones), `package.json`
> dependencies, and `tsconfig` path aliases. It generalizes the shipped Mode-A /
> Mode-B inheritance + the FR-3 Prisma field-set injection into **one** structured
> contract surface — and it is the generation-time **slice of the Mieruka
> `CodeGraph`**, so code-gen coherence and code-observability share one resolver
> rather than building it twice.

---

## 0. Planning Insights (Self-Reflective Update)

> Changes between v0.1 (the postmortem's "build a deterministic scanner" framing) and
> v0.2 (after reading the live seams). The grounding pass revealed that Approach A is
> a **generalization of code that already ships**, not a greenfield primitive — which
> reshapes scope, de-risks effort, and points at the likely Gap-A root cause.

| v0.1 assumption (from the postmortem) | Grounding discovery | Impact |
|---------------------------------------|---------------------|--------|
| Approach A is a new from-scratch scanner | The **first slice already ships**: `upstream_interface.render_prisma_field_sets` + `extract_ts_exports` + `prisma_parser` + `_package_name`, wired through `_collect_upstream_interfaces` → `gen_context["upstream_interfaces"]` → spec_builder | **FR-6** reframed: *generalize and unify the existing extractors into one artifact*, don't rebuild. Effort drops from medium to **small-medium** |
| The schema is "readable but the LLM guessed anyway" | The Prisma field-set injection (Gap-B FR-3) is **heuristic-gated** by `_feature_mirrors_data_model(feature)` and only renders for features that match — PI-001/004/007 plausibly **didn't trigger the heuristic**, so the field set was never injected for them | **FR-3/FR-5**: injection must be **reliably scoped to the entities a feature touches**, not gated by a name/description heuristic that silently skips |
| Gap B needs "more inheritance" | Mode B injects real *exports* but no **canonical module-path table** and no **negative signal** ("there is no `@/lib/prisma`; the client is `@/lib/db`") strong enough to beat the LLM's canonical-name prior; it also can't catch invented **sub-paths** (`@/lib/db/capabilities`) | **FR-4** is a distinct first-class requirement: an authoritative module-path table **with explicit negatives** for the recurring inventions |
| Build it "as the CodeGraph" before implementing | The Mieruka `CodeGraph` Phase 1 is **blocked** (tree-sitter/codebleu pin conflict) and is its own project; blocking Approach A on it stalls a shipping-now fix | **OQ-1 resolved:** converge on the **artifact schema/contract**, not a shared implementation on day one. Ship a minimal producer now (reusing the regex/stdlib extractors, which already exist) that conforms to the schema; Mieruka's `CodeGraph` becomes the production backend later. "Don't pay the integration tax twice" = **one schema**, swappable backend |
| tree-sitter adoption is a prerequisite | tree-sitter is **already a dependency** (`languages/csharp_parser.py` uses it); the pin conflict only blocks the *CodeBLEU* pairing | **FR-7/NFR**: v1 may use the existing regex/stdlib extractors (the "partial-code" tier); tree-sitter/SCIP are documented upgrade paths, not v1 gates |

**Resolved open questions (from this grounding pass):**
- **OQ-1 → Converge on schema, not implementation.** Define `forward_project_knowledge.json` as the shared contract; minimal producer now; Mieruka `CodeGraph` as the later backend. Approach A does **not** block on Mieruka Phase 1.
- **OQ-3 → Extend the existing seam.** Build on `_collect_upstream_interfaces` → `gen_context` → spec_builder (the proven path), not a parallel injection mechanism.

Open questions that remain (OQ-2, OQ-4, OQ-5, OQ-6) are in §6.

---

## 1. Problem Statement & Gap Table

Run-011 (the M4 batch) produced the first **honest** verdict of this session (0.50 /
PARTIAL) because Approach B's classifier signatures now fire. But honesty exposed the
next layer: **5 of 10 features failed on content the LLM invented despite the truth
being on disk.** Mode-A/B inheritance propagates *module paths between same-batch
files* (which worked); it does **not** propagate *which fields an entity has* or
*which import paths are canonical vs hallucinated*.

| Category | What the LLM invented (run-011) | Truth on disk | Covered today? |
|----------|----------------------------------|---------------|----------------|
| **Prisma field names** (Gap A) | `aiRefId`, `label`, `outcomeId`, `title`, `supportingEvidence` | `name`, `category`, `evidence`, `value`, `unit`, … (in `prisma/schema.prisma`) | Partially — FR-3 injection is **heuristic-gated**, skipped these features |
| **Module-import paths** (Gap B) | `@/lib/prisma` (3rd recurrence), `@/lib/db/capabilities`, `@/lib/ai/client` | `@/lib/db` (exports `db`), `@/lib/ai/service` | Mode B injects exports, but no **authoritative path table + negatives** |
| **Dependency availability** | (covered) | `package.json` | Detected by Approach B; **not prevented** at the source |
| **Project config** (tsconfig aliases) | — (latent) | `tsconfig.json` `paths` | Not injected |

Root cause (per `CROSS_FILE_CONTRACT_RESOLUTION.md` §4): **per-file probabilistic
generation (locality).** Each feature is drafted in isolation; absent an authoritative,
structured, *injected* statement of the project's contract surface, the LLM fills gaps
with plausible-canonical guesses from its training distribution. Detection (Approach B)
makes failures honest; **only injection of the truth (Approach A) prevents them.**

---

## 2. Goal

Before a batch generates, build one deterministic, read-only project-knowledge artifact
and inject the **relevance-scoped** subset into every feature's spec prompt as a P0
section, framed authoritatively, so the drafter imports real paths and uses real fields
instead of inventing them — measurably reducing the run-011 failure classes to zero on
re-run, at bounded token cost, and on a schema the Mieruka `CodeGraph` can later produce.

---

## 3. Functional Requirements

### FR-1 — Deterministic project-knowledge artifact
A scanner (no LLM) reads the project at batch start and emits
`forward_project_knowledge.json` into the run's plan-ingestion output, carrying:
1. **Prisma model summary** — per model: `field → {type, nullable, default, id, unique}` and relations.
2. **Module-path table** — per exported symbol/module: its canonical import specifier (e.g. `db → @/lib/db`), derived from on-disk files + `tsconfig` `paths`.
3. **`package.json` snapshot** — declared dependencies + devDependencies (names; versions optional).
4. **`tsconfig` snapshot** — `paths` aliases + the compiler options that change validity (`target`, `lib`, `strict`, `module`, `moduleResolution`).
5. **Per-file export table** — for project source files: exported symbols (reuse `extract_ts_exports`).

*Acceptance:* against the strtd8 project root, the artifact lists `Capability` with exactly its schema fields (no `aiRefId`/`label`), and `modulePaths["db"] == "@/lib/db"`. Built with zero LLM calls. A project missing a `prisma/schema.prisma` or `tsconfig.json` produces a partial artifact (omits that section), never an error.

### FR-2 — Shared schema / resolver contract (CodeGraph convergence)
`forward_project_knowledge.json` MUST conform to a documented schema designed so the
Mieruka `CodeGraph` can produce it as a query result later (the artifact is a *view* of
the CodeGraph, per `CROSS_FILE_CONTRACT_RESOLUTION.md` §11). The producer backend is
swappable behind the schema; v1 ships a regex/stdlib producer (OQ-1).
*Acceptance:* the schema is documented (a `pydantic` model + a JSON-schema/example);
the producer is injected behind an interface (`ProjectKnowledgeProducer` protocol) so a
future `CodeGraph`-backed producer drops in without changing the injection seam.

### FR-3 — Reliable, relevance-scoped injection (replaces the heuristic gate)
The artifact's relevant subset is injected into every feature's spec context as a P0
section via the existing `_collect_upstream_interfaces` → `gen_context` → spec_builder
path. Relevance scope = the feature's `target_files` import-graph closure **plus the
Prisma entities the feature references** — determined structurally, **not** by the
current `_feature_mirrors_data_model` name/description heuristic (which silently skipped
PI-001/004/007).
*Acceptance:* a reproduction of PI-001 (enrich-capabilities) receives the `Capability`
+ `Outcome` field sets in its spec prompt **without** matching any name heuristic; token
cost of the injected section is bounded (FR-9).

### FR-4 — Module-path authority with explicit negatives (closes Gap B)
The injected section states, authoritatively, the canonical import path for each module
a feature is likely to use, **and explicit negatives for the recurring inventions**:
"The Prisma client is imported as `import { db } from '@/lib/db'`. There is no
`@/lib/prisma`, no `@/lib/db/<model>` sub-module, and the AI service is `@/lib/ai/service`
(not `@/lib/ai/client`)." Negatives are generated from the gap between the LLM's known
canonical-name priors and the real module-path table (seed the negative list with the
recurring inventions; extend as new ones surface).
*Acceptance:* a reproduction of PI-002 / PI-007 imports emits only paths present in the
module-path table; the `@/lib/prisma` invention does not recur.

### FR-5 — Prisma field-set authority (closes Gap A)
For each entity a feature touches, the injected section lists the **exact** field set
with types and an explicit instruction: "Use only these fields; do not invent fields
(e.g. no `title`/`aiRefId`/`supportingEvidence`). `Metric` has no FK to `Outcome`."
*Acceptance:* a reproduction of PI-001/004/007 generates `db.<model>.create/update`
calls using only fields in the artifact; the run-011 invented-field set does not recur.

### FR-6 — Subsume the existing extractors (don't build twice)
The artifact producer reuses and unifies the shipped extractors —
`upstream_interface.extract_ts_exports` / `render_prisma_field_sets` /
`render_upstream_interfaces`, `prisma_parser.parse_prisma_schema`,
`cross_file_imports._package_name`. Mode-A sibling-producer inheritance and Mode-B
anchor inheritance become **queries over the same artifact**, not separate code paths.
*Acceptance:* `_collect_upstream_interfaces` is refactored to source Mode-A/B interface
rendering from the artifact; existing Mode-A/B tests
(`test_upstream_interface.py`, `test_mode_b_prisma_inheritance.py`) stay green.

### FR-7 — Two-tier substrate, partial-code tier for v1
The producer operates on **partial / non-building** code (the generation-time reality),
so v1 uses the regex/stdlib (`ast`/`symtable`) extractors that already exist. The
SCIP/buildable tier (post-build, precise) is a documented upgrade path that complements
the `tsc` gate — **out of v1 scope** (see Non-Requirements).
*Acceptance:* the artifact builds correctly when the project does not compile (mid-batch),
without requiring a provisioned toolchain.

### FR-8 — Validation against run-011
*Acceptance (the headline gate):* a reproduction harness regenerates the 5 failed
run-011 features (PI-001, PI-002, PI-004, PI-007, PI-010-field-portion) **with the
artifact injected** and asserts: zero invented Prisma fields (FR-5), zero invented module
paths (FR-4). A baseline run **without** the artifact preserves existing behavior
(regression guard).

### FR-9 — Bounded token cost
The injected section is relevance-scoped (FR-3) and size-bounded; the producer logs the
artifact size and the per-feature injected-token delta. A whole-project artifact must not
be injected wholesale into every feature.
*Acceptance:* the per-feature injected project-knowledge section stays within a declared
budget (e.g. ≤ ~800 tokens for a typical M4 feature); the budget and actual are logged.

### FR-10 — Read-only at generation time
The artifact is read-only during generation. New files a feature introduces are declared
via the existing Mode-A `depends_on` producer set (already handled) and surface to later
features through the artifact's per-file export table — no feature mutates the artifact
mid-batch.
*Acceptance:* concurrent feature generation reads a stable artifact; a producer file
generated by an earlier feature appears in the artifact view consumed by its dependents
(parity with today's Mode-A behavior).

---

## 4. Non-Functional Requirements

- **NFR-1 Deterministic.** No LLM in the producer; same project state → same artifact.
- **NFR-2 Fast & bounded.** One per-batch build; bounded read per feature.
- **NFR-3 Degrade loudly, never falsely.** Missing schema/config/file → omit that
  section + log; never silently inject a wrong/empty truth that the LLM would trust.
- **NFR-4 Language-aware, TS/Prisma-first.** v1 targets the TS + Prisma surface that
  run-008/009/011 failed on; the schema is extensible to Go/Java/C# (pairs with the
  compile-gate roadmap) without rework.
- **NFR-5 Convergence-preserving.** The schema is the Mieruka `CodeGraph` contract;
  do not encode SDK-only assumptions that would block the CodeGraph backend.

---

## 5. Non-Requirements (v1)

- **Not** the full Mieruka `CodeGraph` build (tree-sitter Phase 1 is pin-blocked); v1 is
  the regex/stdlib producer conforming to the shared schema.
- **Not** retiring Approach B's regex signatures — they remain the cheap-now detection
  layer; querying the `CodeGraph` instead is a later convergence.
- **Not** the SCIP / buildable-precise tier (post-build; complements the `tsc` gate).
- **Not** Approach D (single-pass batch synthesis) — a separate, orthogonal lever.
- **Not** changing `clean-prior-run.sh` / the `upstream_anchors` signal — consumed, not built.
- **Not** guaranteeing the LLM *consults* the artifact (a content-level risk, OQ-4) —
  v1 maximizes the odds (P0, structured, authoritative, negatives) and **measures** it
  via FR-8; it does not claim 100% adherence.

---

## 6. Open Questions

- **OQ-2 — Relevance-scoping algorithm.** Import-graph closure of `target_files` + a
  Prisma-entity reference scan? Or a simpler "all entities + the canonical module table"
  (small at strtd8 scale)? Trade token cost vs completeness. *(Plan to resolve.)*
- **OQ-4 — Adherence measurement.** Does P0 + authoritative framing + negatives
  actually move the LLM off its prior? Resolve empirically via the FR-8 re-run; if
  adherence is weak, escalate (e.g. a draft-time self-check or Approach C contract-first).
- **OQ-5 — tree-sitter vs regex for the v1 producer.** tree-sitter is already a dep;
  is its TS-export fidelity worth adopting now, or is `extract_ts_exports` (regex)
  sufficient for v1 given the pin-conflict isolation cost? *(Lean regex for v1.)*
- **OQ-6 — Artifact persistence & staleness.** Rebuild per batch (simple, always fresh)
  vs cache with mtime invalidation (faster, risk of staleness). *(Lean rebuild-per-batch.)*
- **OQ-7 — Negative-signal source (FR-4).** Hard-seed the recurring inventions
  (`@/lib/prisma`, `@/lib/db/<model>`, `@/lib/ai/client`) vs derive from a known-canonical-
  name list. *(Lean: seed now, derive later.)*

---

## 7. Relationship to the roadmap

- **Closes:** RUN-011 Gap A (FR-5) + Gap B (FR-4) at the source; generalizes RUN-008
  Fix 1 (Mode A) and RUN-009 Fix 2 (Mode B) into one artifact (FR-6).
- **Complements:** Approach B (detection) — Approach A injects the truth, B verifies it;
  both will query the same `CodeGraph` after convergence (§11 of the resolution doc).
- **Pairs with:** the verification-ledger consolidation (RUN-011 Gap D, Fix 3) — both
  write into / read from the canonical project surface; can ship independently.
- **Does not gate:** strtd8 M4-M6 delivery (direct-fix + the honest gate proceed in
  parallel); this reduces the direct-fix burden on future batches.

---

*v0.2 — Post-planning self-reflective update: scope reframed from "new scanner" to
"generalize the shipped extractors"; the heuristic-gate identified as the likely Gap-A
miss; OQ-1/OQ-3 resolved (converge on schema not implementation; extend the existing
seam). Pairs with a forthcoming `APPROACH_A_PROJECT_KNOWLEDGE_PLAN.md`. CRP review
offered before implementation.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

> Append-only convergent-review state. New reviewers add a round to **Appendix C**, then
> dispositions are recorded in **Appendix A** (applied) or **Appendix B** (rejected).
> Reviewers: scan A/B/C first and do **not** re-propose settled or rejected items.

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
