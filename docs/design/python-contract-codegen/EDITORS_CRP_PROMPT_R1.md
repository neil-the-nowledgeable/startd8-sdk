# Convergent Review Prompt

**Generated:** 2026-06-12 15:26:08 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/EDITORS_ARCHETYPE_PLAN.md` | 101 lines · 1580 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/EDITORS_ARCHETYPE_REQUIREMENTS.md` | 230 lines · 2342 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/EDITORS_CRP_FOCUS_R1.md` | 25 lines · 244 words |

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

# CRP Focus — `editors:` archetype review (R1)

Weight these concerns; ground every suggestion in the actual `backend_codegen` source where possible.

1. **Drift / idempotency (highest priority).** FR-ED-10/FR-ED-15 rest on a *verified* claim: `fastapi-flow`
   is registered in no drift renderer, so `generate backend --check` exits 1 on a clean `flows:` app.
   Scrutinize: is the proposed editors drift path (S7, `_FORMS_KINDS`/`_check_forms_drift` model with the
   editor name in the `startd8-entity` header slot) actually sufficient for a single-editor byte re-render?
   Are there multi-editor / name-collision / empty-section edge cases that still false-flag drift?

2. **Reset vs. dirty-detection correctness (FR-ED-12).** Is the data-default + "store only if changed"
   rule airtight? Consider: a child whose *legitimate* desired override equals the source/default text;
   concurrent edits; whitespace-only differences; the resolver returning a value that changes between GET
   and POST. Does the rule ever lose a real edit or silently materialize a default?

3. **Security (FR-ED-14, anti-IDOR).** Is the server-side editable-set allow-list complete? Consider the
   parent-id in the route itself (who may open `<route>` for a given parent?), the `filter` being trusted,
   and field-level write scope (only `edit_field`, never other columns via form params).

4. **Seam / interface (FR-ED-9).** Fixed-module resolver convention vs. flows' `on_finish`: is the
   signature `(child_row, session) -> str` right? What about resolver exceptions at request time, and the
   `default_value`-omitted mode (OQ-10)?

5. **Plan completeness / sequencing.** Does every FR map to a step? Is FR-ED-15 truly independently
   shippable? Any missing step (CLI `--check` pass-through, provider entry-point, gates.py interaction)?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/EDITORS_ARCHETYPE_PLAN.md`  ·  **Size:** 101 lines · 1580 words

```markdown
# `editors:` Archetype — Implementation Plan

**Version:** 1.0
**Date:** 2026-06-12
**Tracks:** `EDITORS_ARCHETYPE_REQUIREMENTS.md` (v0.1 → v0.2 after this plan's reflection)
**Status:** Planned (pre-implementation)

> This plan was written by reading the actual `backend_codegen` machinery the archetype must slot into.
> The discoveries (§A) fed the v0.2 self-reflective update of the requirements. **One discovery is a
> verified, pre-existing bug in the `flows:` feature** that this work should fix in passing.

---

## A. Discoveries (planning vs. the v0.1 assumptions)

| v0.1 / brief assumed | Planning revealed (grounded in code) | Impact |
|----------------------|--------------------------------------|--------|
| "Follow the `flows:` precedent and editor files will be `$0`/drift-clean" (FR-ED-10) | **VERIFIED BUG:** `fastapi-flow` is registered in **no** drift renderer map (`drift.py` `_AI/_PAGES/_FORMS/_SETTINGS_KINDS` + `_renderers()`). The flow **router** carries `header_forms` (→ `# GENERATED from` + `schema-sha256`), so `is_owned_generated_file()` = True, drift runs, hits the default path, `_renderers().get("fastapi-flow")` → `None` → **`tampered`**. Confirmed empirically: `generate backend --check` on a `flows:`-using app exits **1** on a clean tree. Shell + aggregator carry no `# GENERATED from`/sha header → silently skipped (also unprotected). | FR-ED-10 cannot "copy flows." Editors **must** register a drift path (the `_FORMS_KINDS`/`_check_forms_drift` model). **New plan step S7.** Also a free **quick win**: register `fastapi-flow` while we're in `drift.py` (S12). |
| `default_value: app.resume_wizard:effective_text` (`module:fn`) (FR-ED-9, OQ-1) | `flows:` `on_finish` is a **bare fn name** imported from a **fixed conventional module** (`flow_generator.py:45` → `from app.flows.finishers import <name>`). Two seam syntaxes in one manifest is avoidable inconsistency, and `module:fn` is unvalidatable at render (arbitrary dotted path). | OQ-1 → adopt the fixed-module convention: `default_value: <bare_fn>` resolved from `app/editors/resolvers.py`. Simpler, consistent, validatable-by-shape. **Updates FR-ED-9.** |
| Pre-fill from effective text **and** "empty → NULL = reset" (FR-ED-4/6, OQ-2) | These collide. If a child with `overrideText IS NULL` is pre-filled with its **source** text and saved unchanged, the POST writes source text into `overrideText` — **materializing a default into an override**, so the field stops tracking the source and reset is defeated. | OQ-2 → require **dirty-detection**: render each input with a `data-default` (the resolved effective value) and on POST **store only inputs that differ from their submitted default; unchanged → leave/!set NULL**. **Updates FR-ED-5/6; new FR-ED-12.** This is the gating correctness decision. |
| Bulk write is "an increment on CRUD" (cheap) | True for the read side (the parent-scoped query already exists: `view_codegen/renderers.py:63,126,166` → `select(Child).where(Child.fk == parent.id).order_by(...)`), but the **bulk multi-row write** is genuinely net-new — CRUD `POST` handlers are single-row (`htmx_generator.py:738/779`). One transaction over N rows + per-row dirty/reset logic is the real new code. | Confirms scope: ~1 new generator module (~router + template), reusing query/filter/POST-parse idioms. Manageable. |
| Mount is free (FR-ED-8) | `main.py` mounts aggregators via **dedicated tolerant blocks** in `render_main` (`crud_generator.py:260-295`), each added when its feature shipped (flows added its own block). `main.py` is always-generated + drift-tracked. | OQ-4 → editors add **one** tolerant block to `render_main` → a **one-time `main.py` byte change (drift) for every existing app** on first regen. Precedented (flows did the same), acceptable, but must be called out. **New FR-ED-13.** |
| (not considered) Mass-assignment (OQ-5) | The bulk POST will receive child ids from the form. Trusting them lets a user edit children of a **different** parent (IDOR) or non-`included` rows. | OQ-5 → the handler must re-derive the editable child set **server-side** (`WHERE fk == parent.id AND filter`) and accept writes **only** for ids in that set; ignore unknown ids. **New FR-ED-14.** No worse than CRUD, but the N-row surface makes it worth enforcing in the archetype. |
| (not considered) Route namespacing (OQ-8) | CRUD owns `/ui/*`, flows own `/flow/*`. Editor `route` is author-supplied free-form (`/resume-wizard/{id}/edit`). Nothing stops a collision with a `views:` route (also free-form) or a future CRUD path. | OQ-8 → validate the route contains exactly one `{id}` placeholder and (cheap) warn on a literal `/ui/`-prefix collision; full cross-section route-uniqueness is a nicety. **Updates FR-ED-2 validation.** |
| Header machinery is enough | `header_forms` (schema+views two-hash) + `header_forms_tmpl` already exist (`_headers.py:115/138`) and the editor name can ride the **`startd8-entity:` header slot** (`embedded_entity()` recovers it in drift). | No new header builder needed — reuse `header_forms`/`header_forms_tmpl` with a new `kind` and the editor name in the entity slot. Enables single-editor drift re-render. |

**Heuristic check:** 6 of 14 requirements changed/added from planning (>30%). The brief was a good
generic shape but under-specified on **idempotency, reset semantics, and security** — exactly where the
deterministic-codegen invariants live.

## B. Architecture & file plan

New module `src/startd8/backend_codegen/editors_manifest.py` (parse, mirror `flows_manifest.py`) and
`src/startd8/backend_codegen/editor_generator.py` (render, mirror `flow_generator.py`).

| Step | File(s) | What | FR |
|------|---------|------|----|
| **S1** | `editors_manifest.py` (new) | `EditorSpec` dataclass + `parse_editors(views_text, known_entities)`; strict keys, dup-name guard, tolerant absence. | FR-ED-1/2 |
| **S2** | `editor_generator.py` (new) | `_validate_editor(schema, spec)` — entity/fk/edit_field/group_by/order_by/filter-key checks (reuse `filters_manifest` + `parse_prisma_schema`); route `{id}` shape + collision warn. | FR-ED-3, OQ-8 |
| **S3** | `editor_generator.py` | `render_editor_router(schema, views, spec)` → `app/editors/<name>.py`: GET (parent 404, `select(child).where(fk==id).where(filter).order_by(order_by)`, group, pre-fill via tolerant resolver import seam) + POST (dirty-detect, reset→NULL, server-side id allow-list, one txn, PRG). Uses `header_forms(..., "fastapi-editor")`. | FR-ED-4/5/6/9/12/14 |
| **S4** | `editor_generator.py` | `render_editor_form(views, spec)` → `app/templates/editors/<name>/form.html`: grouped `<section>`s or flat list; one `<textarea name="item-{id}">` per child with `data-default`. Uses `header_forms_tmpl(..., "editor-form", entity=name)`. | FR-ED-7/12 |
| **S5** | `editor_generator.py` | `render_editors(schema, views)` → list of (path, text) incl. `app/editors/__init__.py` aggregator (`editor_routers`), **with a real `# GENERATED from`/sha header** (avoid the flow-aggregator gap). Empty when no `editors:`. | FR-ED-8 |
| **S6** | `assembler.py:80` | `out.extend(render_editors(schema_text, views_text or ""))` right after `render_flows`. | FR-ED-8/10 |
| **S7** | `drift.py` | Add `"fastapi-editor"` (router) + `"editor-form"` (template) to a views.yaml-derived drift path; extend `_forms_renderers()` (or a sibling `_editors_renderers`) to re-render the **named** editor (recover name from `embedded_entity`). Add kinds to the `forms`-style set so `check_drift` routes them with `forms_text`. | FR-ED-10 |
| **S8** | `crud_generator.py` `render_main` | Add one tolerant `try: from .editors import editor_routers / except ModuleNotFoundError: editor_routers = []` block + mount loop, after the flows block. | FR-ED-8/13 |
| **S9** | `provider.py` / entry points | Ensure editor kinds are recognized as owned (`is_owned_generated_file` already covers header-bearing files; confirm the skip-hook `owned_file_in_sync` now returns True for editor files once S7 lands). | FR-ED-11 |
| **S10** | `cli_generate.py` | No new flag — `editors:` rides the existing `views_text` already threaded to generate **and** `--check` (`forms_text=views_text`, line 288). Confirm pass-through. | FR-ED-10 |
| **S11** | `tests/unit/backend_codegen/test_editors.py` (new) | Parse (strict/tolerant/dup), validation (bad fk/field/entity), render snapshot, **`--check` in_sync round-trip** (the test `flows:` lacks), dirty-detect/reset, IDOR allow-list, resolver-absent fallback, mount-block presence. | all |
| **S12** | `drift.py` (quick win) | Register `fastapi-flow` (+ give the flow shell/aggregator real headers) so `flows:` apps pass `--check`. Add a regression test. **Independently shippable.** | (fixes WIZARD_STEP_STATE) |

## C. Risks & validation

- **R1 — Drift round-trip is the gate.** The single most important test (S11) is generate→`--check`==`in_sync`
  with an `editors:` section present. If S7 is wrong, we reproduce the flows bug. Validate by mirroring
  the empirical check used to find it.
- **R2 — `main.py` one-time drift (FR-ED-13).** Document that the first `generate backend` after this
  ships re-stamps `main.py` for every app. Verify the block is inert (`editor_routers = []`) when no
  `editors:` declared, so behavior is identical for non-editor apps.
- **R3 — Dirty-detection semantics (FR-ED-12).** The correctness crux. Test: child with NULL override,
  pre-filled with source, saved unchanged → `edit_field` stays NULL (not materialized). Child edited →
  stored. Child cleared → NULL.
- **R4 — Resolver contract.** Test the tolerant seam both ways: resolver present (used) and absent
  (falls back to raw `edit_field`, app still serves).

## D. Sequencing

S12 (flows drift quick win) is independent — ship first as a small PR (de-risks the drift machinery and
delivers immediate value to existing `flows:` apps). Then S1→S6 (manifest+generation), S7+S8 (drift+mount),
S9/S10 (wiring), S11 (tests). The whole archetype is ~2 new modules + ~4 touched files.

---

*Plan v1.0 — feeds the v0.2 self-reflective requirements update (§0 Planning Insights).*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/python-contract-codegen/EDITORS_ARCHETYPE_REQUIREMENTS.md`  ·  **Size:** 230 lines · 2342 words

```markdown
# `editors:` Archetype — Bulk Child-Field Editor (Requirements)

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-12
**Status:** Draft (planning-corrected; CRP review pending)
**Component:** `src/startd8/backend_codegen/` (a new editor archetype, sibling to CRUD / `forms:` / `filters:` / `flows:` / `views:`)
**Requested by:** StartDate (strtd8) app team — `docs/SDK_BULK_CHILD_FIELD_EDITOR_CAPABILITY_BRIEF_2026-06-11.md` (strtd8 repo)
**Owner:** startd8-sdk team
**Plan:** `EDITORS_ARCHETYPE_PLAN.md` (v1.0)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 (pre-planning, carrying the brief's assumptions) and v0.2 (after reading the
> `backend_codegen` machinery and empirically testing the closest precedent). The planning pass produced
> **7 corrections + 3 new requirements**, the most important driven by a **verified pre-existing bug**.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| "Follow the `flows:` precedent → editor files are `$0`/drift-clean" (FR-ED-10) | **Verified bug:** `fastapi-flow` is registered in no drift renderer; `generate backend --check` exits **1** on a clean `flows:` app (router → `tampered`; shell/aggregator → silently skipped, unprotected). | Editors **must** register an explicit drift path (the `filters:`/`forms:` model), not copy flows. FR-ED-10 rewritten; **quick win** added (FR-ED-15: fix `flows:` drift). |
| `default_value: module:fn` syntax | `flows:` `on_finish` uses a **bare fn from a fixed module**; two seam syntaxes is needless inconsistency and `module:fn` is unvalidatable at render. | OQ-1 resolved → fixed-module convention (`app/editors/resolvers.py`). FR-ED-9 updated. |
| Pre-fill from effective text **and** empty→NULL reset | These collide — saving an unchanged source-prefilled input **materializes** a default into an override, defeating reset and de-linking from the source. | OQ-2 resolved → **dirty-detection** required. FR-ED-5/6 updated; **FR-ED-12 added**. |
| Mount is free | `main.py` is always-generated + drift-tracked; adding the editor mount block re-stamps it once for every app. | OQ-4 resolved → accept the one-time drift, require inert-when-absent. **FR-ED-13 added**. |
| (not considered) | Bulk POST carries N child ids → IDOR / cross-parent / non-`included` edit surface. | OQ-5 resolved → server-side allow-list. **FR-ED-14 added**. |
| (not considered) | Author-supplied `route` can collide with `/ui/*` (CRUD), `views:`, `/flow/*`. | OQ-8 resolved → validate single `{id}` + warn on `/ui/` collision. FR-ED-2 validation extended. |
| Header machinery insufficient | `header_forms`/`header_forms_tmpl` + the `startd8-entity` slot already enable single-editor drift re-render. | No new header builder; reuse with a new `kind` + editor name in the entity slot. |

**Resolved open questions:**
- **OQ-1 → Fixed-module convention.** `default_value: <bare_fn>` from `app/editors/resolvers.py` (mirrors `flows:` `on_finish`).
- **OQ-2 → Dirty-detection (FR-ED-12).** Inputs carry their resolved default; POST stores only changed values; unchanged stays NULL.
- **OQ-3 → Explicit editors drift path (FR-ED-10).** Reuse the views.yaml-derived (`_FORMS_KINDS`-style) drift route; do **not** rely on the flows path.
- **OQ-4 → Accept one-time `main.py` drift (FR-ED-13).** Precedented by flows; block is inert when no `editors:` declared.
- **OQ-5 → Server-side id allow-list (FR-ED-14).** The handler re-derives the editable set; ignores ids outside it.
- **OQ-6 → `group_by` optional.** Flat ordered list is the v1 floor; grouping is additive.
- **OQ-7 → `<textarea>` for v1.** Widget-from-column-type deferred (non-requirement); `edit_field` is treated as free text.
- **OQ-8 → Route validation (FR-ED-2).** Exactly one `{id}` placeholder; warn on `/ui/` literal collision.

## 1. Problem Statement

The StartDate résumé wizard needs a **final-edit** surface: edit one field (`overrideText`) across a
parent's (`ResumeBuild`) filtered, grouped children (`ResumeBuildItem` where `included == true`,
grouped by `sectionKey`, ordered by `orderIndex`) in **one form/POST**, with reset-to-default. The data
and generator already support it (`ResumeBuildItem.overrideText` exists; the assembler resolves
override-or-source first — FR-RV-3). The **only** gap is the editing surface. The app team could
hand-author it (one route pair + a template in their owned wizard) but has **paused** to let the SDK
own it, because the shape is **generic**, not résumé-specific:

> "Edit a chosen field across a parent's filtered, grouped children, then save (with reset-to-default)."

If `backend_codegen` gains a **bulk child-field editor** archetype, this feature — and every future
"edit the children of X in one screen" — becomes a **manifest declaration**, generated `$0` like
CRUD / views / filters. The only app residue is a tiny app-specific **default-value resolver**.

### Gap table

| Capability | Current State | Gap |
|-----------|---------------|-----|
| Edit `overrideText` per child | Exists on `/ui/resumebuilditem` CRUD (single-row) | No **contextual, parent-scoped, bulk** editor |
| Parent→child FK scoping, `group_by`, `order_by` | Exists in `views:` (board / workspace / aggregate) | Not exposed as an **editable** surface |
| Own-column `filter` (`included == true`) | Exists in `filters:` | Not reused by an editor |
| Bulk multi-row write (one field, N children, one POST) | **Does not exist** — CRUD is single-row write | Net-new generator surface |
| Reset-to-default (empty → fall back) | n/a | Net-new |
| App-provided pre-fill/reset resolver | `flows:` has the `on_finish` owned-fn hook precedent | Needs an analogous `default_value` hook |

## 2. Requirements

### Manifest

- **FR-ED-1 — `editors:` section.** A new top-level `views.yaml` section, a **list** of editor specs,
  sibling to `views:` / `forms:` / `filters:` / `flows:`. Parsed strictly: unknown keys → loud;
  duplicate editor `name` → loud; **inert (zero artifacts) when absent**. Tolerant of an empty/missing
  section (the filters/flows precedent).
- **FR-ED-2 — Grammar.** Each editor declares:

  ```yaml
  editors:
    resume_final_edit:
      parent: ResumeBuild           # context object (id in the route)
      child: ResumeBuildItem        # rows to edit
      fk: resumeBuildId             # child → parent FK column
      edit_field: overrideText      # the single edited field (one <textarea> per child)
      filter: { included: true }    # reuse filters: own-column semantics
      group_by: sectionKey          # form sections (optional)
      order_by: orderIndex          # ordering within/across groups
      reset_to_default: true        # empty input → set edit_field = NULL
      default_value: app.resume_wizard:effective_text   # pre-fill / reset target resolver (§ hook)
      route: /resume-wizard/{id}/edit
      label: Make final edits
  ```

- **FR-ED-3 — Contract validation (loud at render).** `parent`/`child` are known entities; `fk` is a
  column on `child`; `edit_field` is a column on `child`; `group_by`/`order_by` (when present) are
  columns on `child`; `filter` keys are own-columns on `child`. Mirrors `filters:`/`flows:` validation
  posture (parse-time entity check, render-time field check where the schema is available).
  **(v0.2, OQ-8)** Additionally validate `route`: it must contain **exactly one** `{id}` placeholder;
  **warn** (non-fatal) when `route` starts with `/ui/` (CRUD namespace) to surface likely collisions.

### Generation

- **FR-ED-4 — GET editor route.** Generate `GET <route>`: load `parent` by id (404 if absent); query
  `child` rows `WHERE fk == parent.id` AND `filter`, ordered by `order_by`, grouped by `group_by`;
  render a form with **one input per child**, pre-filled from the `default_value` resolver.
- **FR-ED-5 — POST save.** Generate `POST <route>`: parse the form; for each editable child, apply the
  dirty/reset rules (FR-ED-12); commit in **one transaction**; redirect back (PRG, the `forms:`
  post-submit precedent). **(v0.2)** Writes are restricted to the server-derived editable set (FR-ED-14).
- **FR-ED-6 — Reset-to-default.** When `reset_to_default: true`, an **empty** input sets
  `edit_field = NULL` (the row falls back to its default/source value). **(v0.2, OQ-2)** An input left at
  its pre-filled default (non-empty but unchanged) is **not** written — see FR-ED-12; only empty +
  `reset_to_default` writes NULL, only a genuinely changed value writes a string.
- **FR-ED-7 — Template.** Generate the form template (`group_by` → `<section>`s; flat ordered list when
  absent). Carries the GENERATED provenance header.
- **FR-ED-8 — Mount.** Emit a per-editor router + an aggregator (`editor_routers`) that `main.py` mounts
  via a **tolerant** `try: from .editors import editor_routers` block (the `flow_routers` precedent).

### The app seam

- **FR-ED-9 — `default_value` hook.** The pre-fill / reset-target value is each child's **effective**
  value, whose resolution is app-specific (polymorphic over the row). The archetype calls an
  **app-provided resolver** named in the manifest via a **tolerant import seam** (the `flows:`
  `on_finish` precedent): present → used for pre-fill; **absent → fall back to `edit_field` raw**
  (no-op seam, app still works). The resolver signature is `resolver(child_row, session) -> str`.
  **(v0.2, OQ-1 resolved)** `default_value` is a **bare function name** imported from the fixed
  conventional module `app/editors/resolvers.py` (`from app.editors.resolvers import <name>`), mirroring
  `flows:`' `from app.flows.finishers import <name>`. The SDK never imports the resolver at generation
  time — it emits a tolerant runtime import seam in the generated app, preserving `$0`/determinism.

### Determinism & ownership

- **FR-ED-10 — `$0`, idempotent, drift-clean.** Editor artifacts are **owned**, `$0.00`-skip
  recognized, and `generate backend --check` reports them **`in_sync`** immediately after a clean
  generate. **(v0.2, OQ-3 resolved)** This requires an **explicit editors drift path** in
  `drift.py`: register `fastapi-editor` (router) + `editor-form` (template) as views.yaml-derived kinds
  (the `_FORMS_KINDS` / `_check_forms_drift` model), re-rendering the **named** editor (editor name
  recovered from the `startd8-entity:` header slot). The aggregator `app/editors/__init__.py` carries a
  real `# GENERATED from` + sha header so it is either drift-protected or cleanly recognized — **never
  the silent-skip state the flow aggregator/shell fall into.** A generate→`--check` round-trip with an
  `editors:` section present is the acceptance gate.
- **FR-ED-11 — Provider owned-kinds.** Register the editor artifact kind(s) so the prime-contractor
  skip-hook (`owned_file_in_sync`) treats them as `$0.00`-owned. Once FR-ED-10's drift path lands,
  `owned_file_in_sync` returns True for in-sync editor files automatically (it delegates to `check_drift`).
- **FR-ED-12 — Dirty-detection (no accidental materialization).** Each generated input carries its
  resolved **default** (the `default_value` result), e.g. as a `data-default` attribute / hidden mirror.
  On POST, for each editable child: **(a)** submitted value `==` its default → **no write** (leave as-is,
  preserving NULL/source-tracking); **(b)** submitted value empty `and reset_to_default` → set NULL;
  **(c)** submitted value differs from default and non-empty → store the string. This is the correctness
  crux that keeps "reset" meaningful and prevents source text from being frozen into an override.
- **FR-ED-13 — One-time `main.py` re-stamp.** Mounting `editor_routers` adds one tolerant block to the
  always-generated `render_main`, changing `main.py` bytes **once** for every existing app on first regen
  (precedented by `flows:`). The block MUST be inert (`editor_routers = []`) when no `editors:` is
  declared, so runtime behavior is identical for non-editor apps. This drift is documented, expected, and
  resolved by a single `generate backend`.
- **FR-ED-14 — Server-side editable-set allow-list (anti-IDOR).** The POST handler re-derives the
  editable child set on the server (`WHERE fk == parent.id AND filter`) and applies writes **only** to
  children whose id is in that set; ids absent from the set (other parents, non-`included` rows,
  fabricated ids) are **ignored**, not written. No reliance on client-submitted ids for authorization.
- **FR-ED-15 — Quick win: fix `flows:` drift (independently shippable).** Register `fastapi-flow` in the
  drift system and give the flow shell + aggregator real provenance headers, so `generate backend --check`
  reports `in_sync` for `flows:`-using apps. This is a pre-existing bug surfaced by planning (verified:
  clean `flows:` app currently fails `--check` with exit 1). Ship as a small standalone PR ahead of the
  archetype; it de-risks the shared drift machinery the editor archetype reuses.

## 3. Non-Requirements (v1)

- **No multi-field bulk edit.** Exactly one `edit_field` per editor.
- **No child create/delete.** Edit-only over an existing child set (`included == true`); no inline
  add-row / remove-row.
- **No LLM.** Pure deterministic generation (bucket 1).
- **No client-side JS framework.** Plain browser form POST + HTMX, consistent with the rest of
  `backend_codegen`.
- **No tenancy / per-user authorization isolation.** Inherits whatever posture generated CRUD has;
  tenancy is deferred (matches `deployment-mode` Tier B).
- **No cross-parent / global bulk edit.** Always scoped to one `parent` id in the route.

## 4. Open Questions

> **All v0.1 open questions were resolved by the planning pass — see §0 for resolutions.** OQ-1→OQ-8
> are closed. Remaining questions are deferred to CRP review:

- **OQ-9 (CRP) — Resolver provenance.** Should the archetype emit a stub `app/editors/resolvers.py`
  (with the declared fn names as `NotImplementedError` placeholders) to make the seam discoverable, or
  stay fully tolerant (no stub)? Trade-off: discoverability vs. an extra owned file.
- **OQ-10 (CRP) — `default_value` optional?** If omitted, pre-fill from `edit_field` raw with no seam
  at all (the simplest case). Is "no resolver declared" a first-class mode (likely yes; cheap)?

## 5. Quick Wins / Low-Hanging Fruit (surfaced by planning)

1. **FR-ED-15 — `flows:` drift fix.** Independently shippable; fixes a verified CI-breaking bug for
   existing `flows:` apps. The editor work builds the exact machinery anyway.
2. **`default_value`-omitted mode (OQ-10).** A zero-seam editor (just `parent/child/fk/edit_field/route`)
   is trivially derivable and covers simple "edit a plain column across children" cases with no app code
   at all — broader reuse than the résumé motivating case for ~zero extra cost.
3. **Reuse over rebuild.** The parent-scoped query (`view_codegen` board/aggregate), filter WHERE
   (`filters_manifest`), POST-parse + PRG (`htmx_generator`), and header/entity-slot drift machinery all
   already exist — the net-new surface is one transaction-bounded bulk write + dirty/reset logic.

---

*v0.2 — Post-planning self-reflective update. 4 requirements narrowed/corrected (FR-ED-5/6/9/10),
3 added (FR-ED-12/13/14), 1 quick-win added (FR-ED-15), 8 open questions resolved, 2 new CRP-level
questions opened. Centerpiece discovery: a verified pre-existing `flows:` drift bug that reframed
FR-ED-10 and produced FR-ED-15.*

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
