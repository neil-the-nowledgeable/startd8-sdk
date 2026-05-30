# Convergent Review Prompt

**Generated:** 2026-05-30 17:47:22 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/LEAD_CONTRACTOR_REMOVAL_AUDIT.md` | 153 lines · 966 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md` | 220 lines · 2127 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/.crp_focus_lead_removal.md` | 30 lines · 277 words |

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

# Reviewer Focus — Lead-Contractor Elimination (where we need input most)

Context: startd8-sdk is **internal-only today**. The maintainer has decided to take the
breaking change NOW (no external deprecation window) and migrate the internal consumers
(ContextCore, wayfinder) in the same coordinated effort. Weight your review toward these:

1. **Phase correctness & green-independence.** Is the 5-phase plan (§5) ordered correctly, and
   is each phase genuinely green on its own? In particular: can Phase 2 (file renames + internal
   import updates, no shim) truly land without breaking the suite given Phases 4–5 haven't run?
   Are there hidden ordering hazards (e.g. entry-point regeneration, `egg-info`, editable installs)?

2. **`workflow_id` migration mechanism.** Is changing `workflow_id="lead-contractor"` →
   `"primary-contractor"` plus a *transient* legacy-id resolution alias the right approach versus
   alternatives (dual-id support, a one-shot state-file rewriter, or accepting stored-state
   breakage)? What stored artifacts key on the id (ContextCore SpanState, dashboards, task_errors
   dirs) and does FR-4 cover them?

3. **Prime vs Primary distinction.** Does the spec keep `PrimeContractorWorkflow` (batch) and
   `PrimaryContractorWorkflow` (single-task) cleanly separated, or is there any wording/step that
   risks conflating them during the rename (e.g. an import, an entry point, a dashboard, a doc)?

4. **Audit inventory completeness.** Given the goal is a clean final `grep` (NFR-5), is anything
   missing from the audit that would leave a straggler — e.g. `__pycache__`, `SOURCES.txt`,
   `.startd8/task_errors/lead-contractor`, mixin-generated JSON, scripts/, CHANGELOG, or
   non-obvious string forms (`Lead Contractor`, `lead_contractor` in YAML keys/metrics labels)?

5. **Coordinated FR-5+FR-6 breaking-change risk.** What are the failure modes of landing the
   removal together with the internal-consumer edits across separate repos (no shared CI)? Is the
   "land together" coordination gate sufficient, or is a brief transient alias still warranted to
   de-risk the cross-repo cutover?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/LEAD_CONTRACTOR_REMOVAL_AUDIT.md`  ·  **Size:** 153 lines · 966 words

```markdown
# Lead-Contractor Usage Audit (Deliverable 1)

**Version:** 1.0
**Date:** 2026-05-30
**Scope:** Every `lead-contractor` / `lead_contractor` / `LeadContractor` reference across the
startd8 SDK repository (code, tests, docs, workflows, entry points, dashboards, identifiers).
**Companion:** `LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md` (the phased-removal spec built on this).
**Method:** `grep -riE "lead[-_ ]?contractor|leadcontractor"` over `src/ tests/ docs/ scripts/`
plus `pyproject.toml`, `.startd8/workflows/`, `dashboards/`, `startd8-mixin/`. Throwaway
`.claude/worktrees/*` copies are **excluded** (auto-cleaned agent worktrees, not source).

---

## 0. Executive summary

The Lead→Primary rename is **half-complete**. A prior "Phase 4 rename" renamed every **class**
to `Primary*` and added **4 backward-compat aliases**, but left the entire `lead` *surface*
intact: 4 module **file names**, the 4 aliases, the runtime `workflow_id="lead-contractor"`,
2 public **entry points**, installed workflow **YAMLs**, **dashboards**, and ~870 prose/comment
references across code, tests, and docs.

| Area | Files | Match lines | Nature |
|------|-------|-------------|--------|
| `src/` | 31 | 116 | 4 file names, 4 aliases, 1 `workflow_id`, rest = docstrings/comments |
| `tests/` | 21 | 268 | 2 lead-named test files; rest reference imports/ids |
| `docs/` | 73 | 415 | design docs, READMEs, lessons references |
| `scripts/` | 18 | 71 | runner scripts, dashboards provisioning |
| entry points | `pyproject.toml` | 2 (+2 ctx) | **public API** (`lead-contractor`, `lead-contractor-contextcore`) |
| installed workflows | `.startd8/workflows/` | 2 files | `lead-contractor.yaml`, `lead-contractor-contextcore.yaml` |
| dashboards | 3 | — | `dashboards/lead-contractor-progress.json`, `startd8-mixin/dashboards/lead_contractor.libsonnet`, `startd8-mixin/generated/dashboards/lead-contractor.json` |

**Key facts that shape removal (see Requirements §0):**

1. **`prime` ≠ `primary`.** `PrimeContractorWorkflow` (batch / multi-feature,
   `prime_contractor_workflow.py`) is a **separate** workflow from `PrimaryContractorWorkflow`
   (single-task lead/drafter pattern, in `lead_contractor_workflow.py`). Both survive; only
   "lead" is eliminated. The single-task workflow's canonical name is **Primary**.
2. **`Secondary`/`Tertiary` do not exist.** The "primary/secondary/tertiary" scheme was only
   *partially conceived* — only `Primary` was implemented. Removal standardizes on `Primary`;
   it does **not** introduce secondary/tertiary.
3. **`lead-contractor` is a public, downstream-consumed API.** It is a registered entry point
   and the runtime `workflow_id`; `MEMORY.md` records **ContextCore** and **wayfinder** as
   downstream consumers of "LeadContractor scripts." Hard removal is a **breaking change**.

---

## 1. Source code (`src/`) — the load-bearing surface

### 1.1 Module files named `lead_contractor*` (must be renamed)

| File | Defines (canonical) | Lead remnant |
|------|---------------------|--------------|
| `src/startd8/workflows/builtin/lead_contractor_workflow.py` | `class PrimaryContractorWorkflow` | filename; `LeadContractorWorkflow = PrimaryContractorWorkflow` (L1821); `workflow_id="lead-contractor"` (L221) |
| `src/startd8/workflows/builtin/lead_contractor_models.py` | `PrimaryContractorConfig`, `PrimaryContractorResult` | filename; module docstring |
| `src/startd8/workflows/builtin/lead_contractor_contextcore_workflow.py` | `class PrimaryContractorContextCoreWorkflow(PrimaryContractorWorkflow)` | filename; `LeadContractorContextCoreWorkflow = ...` (L539) |
| `src/startd8/contractors/generators/lead_contractor.py` | `class PrimaryContractorCodeGenerator` | filename; `LeadContractorCodeGenerator = PrimaryContractorCodeGenerator` (L669) |

### 1.2 Backward-compat aliases (the actual `Lead*` symbols still importable)

| Alias (= canonical) | Location |
|---------------------|----------|
| `LeadContractorWorkflow = PrimaryContractorWorkflow` | `lead_contractor_workflow.py:1821` |
| `LeadContractorContextCoreWorkflow = PrimaryContractorContextCoreWorkflow` | `lead_contractor_contextcore_workflow.py:539` |
| `LeadContractorCodeGenerator = PrimaryContractorCodeGenerator` | `generators/lead_contractor.py:669`; re-exported `generators/__init__.py:8,12` |
| `LeadContractorChunkExecutor = PrimaryContractorChunkExecutor` | `contractors/artisan_phases/development.py:2812` |

### 1.3 Public-surface registrations (workflow discovery)

| Item | Location | Notes |
|------|----------|-------|
| `workflow_id="lead-contractor"` | `lead_contractor_workflow.py:221` | **runtime ID** — self-reported even when loaded via the `primary-contractor` entry point. Referenced by stored state, dashboards, downstream lookups. |
| entry point `lead-contractor` | `pyproject.toml:101` | → `lead_contractor_workflow:LeadContractorWorkflow` |
| entry point `lead-contractor-contextcore` | `pyproject.toml:102` | → `...:LeadContractorContextCoreWorkflow` |
| entry point `primary-contractor` | `pyproject.toml:99` | → `PrimaryContractorWorkflow` (the canonical replacement, already present) |
| entry point `primary-contractor-contextcore` | `pyproject.toml:100` | canonical replacement, already present |
| `__init__.py` lazy loader + `__all__` | `workflows/builtin/__init__.py:13,15,35,37,70-78` | exports BOTH `PrimaryContractorWorkflow` and `LeadContractorWorkflow` |

### 1.4 Prose / comment / docstring references (no behavior; cleanup only)

`implementation_engine/`: `models.py:5,54`, `spec_builder.py:1433`, `engine.py:5,37`,
`drafter.py:1128`, `reviewer.py:4,497`, `__init__.py:5` — all describe code as "extracted from
`LeadContractorWorkflow`."
`contractors/`: `queue.py:30,201`, `context_seed/core.py:659,1413,2428`,
`artisan_phases/development.py:1171,1220,1255`, `generators/__init__.py`, `README.md`.
Cross-refs: `forward_manifest.py:583` ("mirrors the lead-contractor path"),
`integrations/contextcore.py:1223` (example agent id `"lead-contractor"`),
`prompts/contractor_prompts.yaml:4` ("replaces the former lead_contractor.yaml"),
`prime_contractor_workflow.py:7,152`, `plan_ingestion_workflow.py:2520`,
`domain_preflight_workflow.py:427`.

### 1.5 Generated/packaging artifacts (regenerated, not hand-edited)

`src/startd8.egg-info/entry_points.txt` (L39-40,45-47) and `SOURCES.txt` — regenerate from
`pyproject.toml` + file renames; not edited directly.

---

## 2. Tests (`tests/`)

**Lead-named test files (rename + retarget):**
- `tests/unit/test_lead_contractor_workflow.py`
- `tests/unit/contractors/test_lead_contractor_executor.py`

**Other test files referencing lead-contractor imports/ids (19):** `test_edit_mode_regression.py`,
`test_truncation_detection.py`, `test_prime_task_enrichment.py`, `test_async_workflows.py`,
`test_prime_contractor_workflow_adapter.py`, `workflows/conftest.py`,
`workflows/test_prime_prompt_externalization.py`, and `contractors/`:
`test_kaizen_response_capture.py`, `test_implement_manifest.py`, `test_design_implement_handoff.py`,
`test_path_resolution.py`, `test_multi_file_edit_fixes.py`, `test_handoff_improvements.py`,
`test_artisan_prompt_improvements.py`, `test_call_graph_pipeline.py`,
`test_development_importable_modules.py`, `test_walkthrough_mode.py`, `test_pca_p0.py`,
`test_implement_prompt_externalization.py`.

---

## 3. Installed workflows, dashboards, scripts

| Artifact | Path |
|----------|------|
| Installed workflow YAML | `.startd8/workflows/lead-contractor.yaml` (`workflow_id: lead-contractor`, `name: Lead Contractor Workflow`) |
| Installed workflow YAML | `.startd8/workflows/lead-contractor-contextcore.yaml` |
| Grafana dashboard | `dashboards/lead-contractor-progress.json` |
| Mixin source | `startd8-mixin/dashboards/lead_contractor.libsonnet` |
| Generated dashboard | `startd8-mixin/generated/dashboards/lead-contractor.json` |
| Scripts | 18 files under `scripts/` (runner/provisioning) reference the id/name |

---

## 4. Out-of-repo (downstream) consumers — coordination required

Per `MEMORY.md`:
- **ContextCore** — LeadContractor scripts (TUI, phase3, runner).
- **wayfinder** — LeadContractor + integration backlog pipeline.

These import `LeadContractor*` symbols and/or invoke the `lead-contractor` workflow id/entry
point. **Hard removal breaks them** unless migrated first. Because startd8-sdk is **internal-only
today**, the requirements (v0.3) take the breaking change *now* and migrate these consumers in the
**same coordinated effort** (land removal + consumer updates together) rather than carrying a
multi-version deprecation window. This set is from `MEMORY.md` and MUST be re-verified live at
kickoff. See Requirements FR-6 / §0 (OQ-3).

---

## 5. Reference classification (drives phase ordering)

| Class | Examples | Behavior risk | Removal phase |
|-------|----------|---------------|---------------|
| **A. Prose/comments/docstrings** | §1.4 | none | Phase 1 (safe, immediate) |
| **B. Internal file names + internal imports** | §1.1 | none if shimmed | Phase 2 (rename + shim) |
| **C. Public aliases / entry points / `workflow_id`** | §1.2, §1.3 | **breaks downstream** | Phase 3 (deprecate) → Phase 5 (remove) |
| **D. Tests** | §2 | none (retarget to canonical) | tracks Phases 1-2 |
| **E. Artifacts (yaml/dashboards)** | §3 | dashboards key on `workflow_id` | Phase 4 (re-key with the id migration) |
| **F. Downstream (out of repo)** | §4 | breaks consumers | Phase 3 (coordinate) before Phase 5 |
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/LEAD_CONTRACTOR_REMOVAL_REQUIREMENTS.md`  ·  **Size:** 220 lines · 2127 words

```markdown
# Lead-Contractor Elimination — Requirements

**Version:** 0.3 (Internal-only decision — break now, no external deprecation window)
**Date:** 2026-05-30
**Status:** Reviewed against the codebase audit (`LEAD_CONTRACTOR_REMOVAL_AUDIT.md`); scope
decision applied (startd8-sdk is internal-only today — take the breaking change now)
**Component:** startd8 SDK — `workflows/builtin/`, `contractors/`, `implementation_engine/`,
entry points, installed workflows, dashboards, tests, docs.
**Goal:** Eliminate the "lead contractor" concept entirely. Standardize the single-task
lead/drafter workflow on the name **Primary**; preserve all behavior via the existing
`Prime`/`Primary` contractor paths.

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between the naive v0.1 view ("lead is dead weight — rename the files and delete
> the aliases") and v0.2, after the codebase audit (`LEAD_CONTRACTOR_REMOVAL_AUDIT.md`).

| v0.1 Assumption | Audit Discovery | Impact |
|-----------------|-----------------|--------|
| Lead/Primary rename is unfinished and messy | The **class** rename is **done** — every class is `Primary*`; only a thin *surface* remains (4 file names, 4 aliases, 1 `workflow_id`, 2 entry points, prose) | Scope narrows from "rename" to "remove the residual lead surface" |
| "primary/secondary/tertiary" scheme is half-built | **Only `Primary` exists.** No `Secondary`/`Tertiary` anywhere | Target naming is **just `Primary`**; do NOT introduce secondary/tertiary (FR-NR) |
| `lead` and `prime` are the same thing being renamed | `PrimeContractorWorkflow` (batch) is a **separate, active** workflow from `PrimaryContractorWorkflow` (single-task, ex-Lead) | Both survive; removal must not conflate them (FR-1) |
| `lead-contractor` is internal | It is a **public entry point** + the runtime `workflow_id`, and **ContextCore + wayfinder consume it downstream** | Hard removal is breaking → needs a **deprecation window + downstream migration** before removal (FR-5, FR-6) |
| One file to rename | **Four** module files + **four** aliases + 2 installed YAMLs + 3 dashboards + 21 test files | Phased plan with import shims, not a single sweep |
| Dashboards are cosmetic | Dashboards/state key on `workflow_id="lead-contractor"` | The `workflow_id` migration is a coordinated step, not a string swap (FR-4) |
| External users will need a deprecation window | **startd8-sdk is internal-only today** (maintainer-controlled consumers only) | **Break now**, no external window; remove the lead surface outright + migrate internal consumers in the same effort (OQ-3) |

**Resolved open questions:**
- **OQ-1 → Keep `Primary`; do not add secondary/tertiary.** The scheme was never built.
- **OQ-2 → `Prime` and `Primary` are distinct and both stay.** Only `Lead` is removed.
- **OQ-3 → `lead-contractor` is internal-only today; take the breaking change NOW.** **(Scope
  decision, 2026-05-30.)** startd8-sdk has no external consumers yet — the only consumers are
  internal projects the maintainer controls (ContextCore, wayfinder). Rather than carry a
  multi-version external deprecation window (and let future external users inherit the tech
  debt), remove the lead surface outright, coordinating the internal consumers in the **same
  effort**. This supersedes the v0.2 "deprecate-then-remove over N minor versions" stance:
  there is no external-user window to honor.
- **OQ-4 → `workflow_id` change is breaking for stored state/dashboards.** Migrate it to
  `primary-contractor`; keep a **transient** legacy-id resolution alias only for the lifetime
  of the internal-consumer migration (one coordinated change), not as a long-lived shim.
- **OQ-5 → Pre-1.0 (`0.4.0`), internal-only.** SemVer permits breaking changes freely; with no
  external users, deprecation *warnings* are unnecessary — a coordinated breaking change across
  the internal projects is cleaner than warning scaffolding nobody external will read.

---

## 1. Problem Statement

"Lead contractor" is the **precursor** name for what is now the **Primary** contractor (the
single-task lead/drafter workflow). A prior rename converted the classes to `Primary*` but left
a residual `lead` surface that is a standing source of accidental complexity and regression risk:
dual names for one concept, a `workflow_id` that disagrees with its entry-point name, stale
docstrings that send readers to nonexistent `Lead*` symbols, and 21 test files anchored on the
old name. The goal is to remove the lead surface **completely** while preserving behavior through
the canonical `Primary` (single-task) and `Prime` (batch) paths.

| Surface | Today | Target |
|---------|-------|--------|
| Single-task workflow class | `PrimaryContractorWorkflow` + `LeadContractorWorkflow` alias | `PrimaryContractorWorkflow` only |
| Module files | `lead_contractor_*.py` (×4) | `primary_contractor_*.py` (×4) |
| Backward-compat aliases | `LeadContractor{Workflow,ContextCoreWorkflow,CodeGenerator,ChunkExecutor}` | removed (after deprecation) |
| Runtime id | `workflow_id="lead-contractor"` | `workflow_id="primary-contractor"` (with legacy-id resolution shim) |
| Entry points | `lead-contractor`, `lead-contractor-contextcore` + `primary-*` | `primary-*` only (after deprecation) |
| Installed YAMLs / dashboards | `lead-contractor*` | `primary-contractor*` |
| Prose / tests / docs | ~870 references | zero "lead" references outside a documented deprecation note |

**Non-goal:** changing *what the workflow does*. This is a naming/structure elimination with
**behavior preserved**, verified by the existing test suite passing throughout.

---

## 2. Functional Requirements

- **FR-1 Preserve the two distinct workflows.** `PrimeContractorWorkflow` (batch, the active
  construction path) and `PrimaryContractorWorkflow` (single-task) MUST both remain fully
  functional and clearly distinguished. Nothing in this work merges, renames across, or
  otherwise conflates `Prime` and `Primary`. *Acceptance:* both workflows resolve and execute
  after every phase; their tests pass unchanged in behavior.

- **FR-2 Rename the four `lead_contractor*` module files to `primary_contractor*`.** Rename via
  `git mv` (preserve history): `lead_contractor_workflow.py` → `primary_contractor_workflow.py`,
  `lead_contractor_models.py` → `primary_contractor_models.py`,
  `lead_contractor_contextcore_workflow.py` → `primary_contractor_contextcore_workflow.py`,
  `contractors/generators/lead_contractor.py` → `contractors/generators/primary_contractor.py`.
  All **internal** imports update to the new paths. *Acceptance:* `grep -rl "lead_contractor"`
  over `src/` returns only the deprecation shim (FR-5) and intentional deprecation notes.

- **FR-3 Purge prose/comment/docstring references (zero behavior).** Every docstring, comment,
  and string that names `LeadContractor*` / "lead contractor" / "lead-contractor path" for
  *descriptive* purposes is updated to the `Primary`/`Prime` name it actually refers to (audit
  §1.4, §1.5 prose). The example agent id in `integrations/contextcore.py:1223` changes to a
  neutral example. *Acceptance:* no `src/` docstring or comment references a `Lead*` symbol that
  no longer exists.

- **FR-4 Migrate the runtime `workflow_id` to `primary-contractor`.** Change
  `workflow_id="lead-contractor"` → `"primary-contractor"`, and re-key the installed YAMLs and
  dashboards to match (audit §3, §5-E). Because pre-existing ContextCore state files may carry the
  old id, the registry SHOULD provide a **transient** legacy-id alias resolving `"lead-contractor"`
  → primary **for the single coordinated migration only** (not a long-lived shim, not a warning
  emitter). It is removed in the same effort once internal state is re-emitted. *Acceptance:* a
  lookup by `"primary-contractor"` resolves natively; any retained legacy alias is explicitly
  time-boxed and removed by the end of the removal effort; dashboards render against the new id.

- **FR-5 Remove the public `Lead*` aliases and entry points outright (no external window).** The
  four aliases (`LeadContractorWorkflow`, `LeadContractorContextCoreWorkflow`,
  `LeadContractorCodeGenerator`, `LeadContractorChunkExecutor`) and the two entry points
  (`lead-contractor`, `lead-contractor-contextcore`) are **removed** — not deprecated over a
  window. startd8-sdk is internal-only (OQ-3), so there is no external consumer to warn; the
  internal consumers are migrated in the same effort (FR-6). Removal updates `pyproject.toml`,
  `workflows/builtin/__init__.py` (`__all__` + lazy loader), and `generators/__init__.py`.
  *Acceptance:* `grep -r "LeadContractor"` over `src/` returns nothing; no `lead-contractor*`
  entry point remains in `pyproject.toml`.

- **FR-6 Migrate the internal consumers in the same coordinated effort.** **ContextCore** and
  **wayfinder** (the only consumers — maintainer-controlled) MUST be retargeted from
  `LeadContractor*` / `lead-contractor` to the `Primary` names / `primary-contractor` id as part
  of this effort, not behind a multi-version gate. This requirement is a **coordination gate**
  on FR-5's removal landing (the removal and the consumer updates ship together so nothing is
  ever broken in a shared working state), but it is **not** a long-lived deprecation window.
  *Note:* the downstream-consumer set is taken from `MEMORY.md` and MUST be re-verified live at
  kickoff (the consumers may have changed). *Acceptance:* a checklist enumerating each internal
  consumer's `lead`→`primary` edits is complete and both repos are green concurrently with FR-5.

- **FR-7 Rename and retarget the lead-named tests.** `test_lead_contractor_workflow.py` →
  `test_primary_contractor_workflow.py` and `test_lead_contractor_executor.py` →
  `test_primary_contractor_executor.py` (via `git mv`); update imports/ids in those and the 19
  other test files that reference the old name to the canonical symbols. A **single** retained
  test asserts the deprecation shim (FR-4/FR-5) warns-and-resolves during the window.
  *Acceptance:* the full suite passes; only the deprecation-shim test references `lead`.

- **FR-8 Update documentation.** `CLAUDE.md`, `src/startd8/contractors/README.md`, and design
  docs that describe the workflow by its old name are updated to `Primary`/`Prime`. Historical
  design docs that *record* the rename keep their text but gain a one-line "superseded — see
  Primary" note rather than being rewritten. *Acceptance:* `CLAUDE.md` and the contractors README
  contain no stale `Lead*` API references.

- **FR-9 Phased, independently-shippable delivery.** The removal ships in ordered phases, each
  green on its own (see §5). No phase leaves the tree in a non-building state. *Acceptance:* the
  test suite passes at the end of every phase.

---

## 3. Non-Functional Requirements

- **NFR-1 Behavior parity.** Zero functional change. The same inputs produce the same generated
  code, costs, and review outcomes before and after. Verified by the existing suite (no behavior
  assertions are weakened to make tests pass).
- **NFR-2 History preservation.** File renames use `git mv` so blame/history survive.
- **NFR-3 No *silent* breakage; intentional coordinated breakage is acceptable.** With no
  external consumers, a multi-version `DeprecationWarning` window is **not** required. Instead,
  breakage is prevented by *coordination*: FR-5's removal lands together with FR-6's internal
  consumer updates, so the shared working set is never left broken. The breaking change is
  recorded in the changelog/release notes with the `lead`→`primary` mapping.
- **NFR-4 Single source of truth.** After completion there is exactly one name per concept:
  `Prime` (batch), `Primary` (single-task). No alias, no second spelling.
- **NFR-5 Auditable completion.** A final `grep -riE "lead[-_ ]?contractor"` over
  `src/ tests/ docs/ scripts/ pyproject.toml .startd8/ dashboards/ startd8-mixin/` returns only
  (a) the time-boxed deprecation shim + its test, and (b) historical design-doc notes — and these
  are enumerated in the completion record.

---

## 4. Non-Requirements

- Does **not** introduce `Secondary`/`Tertiary` contractor concepts (they were never built; the
  target is `Primary` only).
- Does **not** merge, rename, or alter `PrimeContractorWorkflow` (batch) — it is out of scope
  except where it *references* the lead name in prose (FR-3).
- Does **not** change workflow behavior, prompts' semantics, cost logic, or review logic.
- Does **not** rewrite historical design docs that record the original lead-contractor design
  (they are annotated as superseded, not deleted — institutional memory).
- Does **not** maintain a multi-version external deprecation window or `DeprecationWarning`
  scaffolding — startd8-sdk is internal-only today and the breaking change is taken now (OQ-3).
- Does **not** land FR-5's removal without FR-6's internal-consumer updates in the same effort
  (coordination gate — prevents a broken shared state, not a deprecation window).

---

## 5. Phased Delivery Plan

| Phase | Scope | Behavior risk | Gate |
|-------|-------|---------------|------|
| **Phase 0** | Audit (`LEAD_CONTRACTOR_REMOVAL_AUDIT.md`) — **done** | none | — |
| **Phase 1** | FR-3, FR-8 prose/docstring/comment + doc cleanup (no code paths) | none | suite green |
| **Phase 2** | FR-2 `git mv` file renames + internal import updates + FR-7 test renames. Update **all internal `src/` imports** to the new module paths directly (no long-lived `lead_contractor_*.py` shim — internal-only). | none (imports updated in-tree) | suite green |
| **Phase 3** | FR-4 `workflow_id` → `primary-contractor`; re-key installed YAMLs + dashboards; regenerate mixin. Add the **transient** legacy-id alias only if pre-existing state files require it for the migration window. | dashboards re-point | dashboards render on new id |
| **Phase 4** | FR-6 prepare internal-consumer (ContextCore, wayfinder) `lead`→`primary` edits (verified live at kickoff) | none in this repo | consumer edits staged/green |
| **Phase 5** | FR-5 remove aliases + entry points outright, **landing together with** the Phase-4 consumer updates; drop any transient legacy alias | breaking (coordinated, no external window) | FR-5/NFR-5 grep clean; all internal repos green concurrently |

Each phase is a separate PR/commit set, green independently (FR-9). Phases 1–3 are non-breaking
and can land immediately; Phases 4–5 land together as the single coordinated breaking change.

---

## 6. Open Questions

*All open questions (OQ-1 … OQ-5) are resolved — see §0.* The v0.2 carry-over (deprecation
window length) is **moot** under the internal-only decision: there is no external window. The
one remaining kickoff action is operational, not a design question:

- **OQ-6 → RESOLVED (no window).** Single coordinated breaking change. Land Phases 1–3
  immediately (non-breaking); land Phases 4–5 together (the one breaking change) in the same
  release (target `0.5.0`). The only kickoff step is **re-verifying the live internal-consumer
  set** (FR-6) since it's sourced from `MEMORY.md`.

---

*v0.3 — Internal-only scope decision applied. The maintainer chose to take the breaking change
now (no external users yet) rather than carry tech debt for future external users. This removes
the multi-version deprecation window and `DeprecationWarning` scaffolding (NFR-3 reframed): FR-5
removes the lead surface outright, and FR-6 becomes a same-effort coordination gate (land removal
+ internal-consumer updates together) rather than a long-lived deprecation gate. FR-4's legacy-id
alias is now transient (migration-window only). Phases 4–5 collapse into one coordinated breaking
change. Paired with `LEAD_CONTRACTOR_REMOVAL_AUDIT.md` v1.0.*

*v0.2 — Post-audit self-reflective update. Scope narrowed from "finish a messy rename" to
"remove a residual public surface"; 5 open questions resolved; discovered `lead-contractor` is a
consumed public API.*
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
