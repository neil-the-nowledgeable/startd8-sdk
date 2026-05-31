# Convergent Review Prompt

**Generated:** 2026-05-31 18:45:05 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_PROJECT_PLAN.md` | 128 lines · 951 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_PROJECT_REQUIREMENTS.md` | 298 lines · 2803 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/private/tmp/crp-focus-cat45.md` | 32 lines · 319 words |

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

## Combined review — cats 4 (project) & 5 (AI-agent) share the descriptor-registry spine

These two docs were written to converge on ONE mechanism: the `_OTEL_DESCRIPTORS` manifest +
a shared schema change (add `category`/`orientation`) + a descriptor↔emission parity test. Weight
these CROSS-DOC concerns most:

1. **Spine consistency.** Do AI-agent REQ-AAO-004/008/012 and project REQ-PRO-002/005 describe the
   SAME schema change (category/orientation on MetricDescriptor/SpanDescriptor) and the SAME parity
   test — or do they diverge / duplicate? Is it specified once and referenced, or twice with drift
   risk? Should there be a single shared requirement both reference?

2. **The two "cede" patterns differ — are both correct?** Cat 5 (AI-agent): the SDK EMITS its own
   metrics, so it is its own "declare-don't-guess" producer (dissolves taxonomy REQ-OAT-025 for SDK
   metrics). Cat 4 (project): the SDK PRODUCES raw signals but ContextCore OWNS the gauges +
   burndown (a cede). Is this asymmetry (emit vs cede) coherent, and does each doc state its
   boundary precisely enough to implement? Does the cat-4 cede mirror the taxonomy capability_index
   cede (REQ-OAT-011 honest-skip with skip_reason=owned_elsewhere)?

3. **Naming/registry alignment with the taxonomy.** The taxonomy (v0.5) just mandated a single
   type-keyed registry with declared_type vs runtime_type and category/orientation as projections.
   Do these cat-4/5 metric descriptors fit that registry model, or do they introduce a parallel
   metric-side registry? Does cat-5's dotted-vs-underscore naming (REQ-AAO-003) and cat-4's
   work-item-vs-codegen "task" collision (REQ-PRO-008) interact?

4. **Sequencing / shared phases.** Both plans have a "descriptor schema keystone" + parity test the
   plans say to "land once, shared." Is that shared step concretely sequenced, or will two PRs each
   add it? Any ordering hazard between the cat-4/5 work and the taxonomy code-alignment?

5. **Deferred-vs-in-scope boundaries.** Cat 5 defers metric-ify of nothing (it already emits); cat 4
   defers metric-ify of Kaizen/velocity JSON (post-run async) and cedes progress to ContextCore. Are
   the deferral lines drawn so the in-scope work is genuinely small and the deferred work is clearly
   someone else's / later?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_PROJECT_PLAN.md`  ·  **Size:** 128 lines · 951 words

```markdown
# Project Observability — Implementation Plan

**Date:** 2026-05-31
**Status:** Plan v0.1 (paired with `OBSERVABILITY_PROJECT_REQUIREMENTS.md` v0.2)
**Scope:** SDK modules — `observability/manifest.py` + `collector.py`, `otel_conventions.py`,
`contractors/artisan_phases/runner.py` + `artisan_contractor.py`, `contractors/development.py`,
`complexity/classifier.py`, doc/comments on `task_tracking_emitter.py` + `integrations/contextcore.py`.
The **category-4 artifact generator** and the **burndown/velocity dashboards** are out of scope
(generator = taxonomy REQ-OAT-041; dashboards = ceded to ContextCore + tracker skills).
**Branch:** `feat/observability-followup-run007` (or a fresh branch).

---

## Guiding principle

Planning showed category-4 is mostly **documentation + declaring existing spans** in the *one shared*
descriptor manifest — the ownership seam is already clean in code, and the heavy lifting (metrics,
live progress) is deferred or ContextCore's. Distill first; declare, don't build. The schema change
that carries `category`/`orientation` is **shared with the AI-agent doc** — land it once.

```
Phase 0  Cleanups / distillation                  C-1, C-2, C-4
Phase 1  Shared keystone: descriptor schema fields  REQ-PRO-002/005 (= AI-agent REQ-AAO-004; ONE change)
Phase 2  Declare the project spans                  REQ-PRO-002, 008
Phase 3  Document the ownership boundary            REQ-PRO-001, 004
Phase 4  Declare delivery signals + SLIs (authored)  REQ-PRO-003a, 006, 007
Phase 5  (deferred) metric-ify; live progress        REQ-PRO-003b (L); progress = ContextCore
```

---

## Phase 0 — Cleanups / distillation

| Step | Change | Files | Removes |
|------|--------|-------|---------|
| 0.1 | Disambiguate the two "task" concepts — rename codegen `task.*` span attrs to `codegen.task.*` (or keep `task.*` for work-items and namespace the chunk attrs), and document the split | otel_conventions.py, development.py, runner.py | C-1 (REQ-PRO-008) |
| 0.2 | Remove the **dead** tier histogram in `complexity/classifier.py:23–35` (created, never recorded) — or wire a `record()` if tier-rate is wanted | complexity/classifier.py | C-2 |
| 0.3 | Reconcile/document the phase-span naming (`artisan.workflow.{id}.phase.{phase}` vs `phase.{type}.attempt.{n}`) | artisan_contractor.py, runner.py | C-4 |

**Validation:** suite green; the renamed attrs are emitted under the new names; no consumer of the
old codegen `task.*` names remains (grep).

---

## Phase 1 — Shared keystone: descriptor schema fields (REQ-PRO-002/005 = AAO-004)

| Step | Change | Files |
|------|--------|-------|
| 1.1 | Add `category` + `orientation` fields to `MetricDescriptor`/`SpanDescriptor` (additive defaults). **This is the same change the AI-agent doc specifies (REQ-AAO-004)** — land it once; both categories consume it | observability/manifest.py |

**Cross-doc:** sequence so this is shared with the AI-agent plan's Phase-0.4/1.1, not done twice.
**Validation:** existing descriptors still construct; `generate_manifest()` includes the new fields.

---

## Phase 2 — Declare the project spans (REQ-PRO-002, 008)

| Step | Change | Files |
|------|--------|-------|
| 2.1 | Declare the already-emitted `phase.*` and `codegen.task.*` span attributes in `_OTEL_DESCRIPTORS` with `category=project_observability`, `orientation=system` | runner.py, artisan_contractor.py, development.py |
| 2.2 | Add those modules to `collector.py._INSTRUMENTED_MODULES`. **Do NOT** add `task_tracking_emitter` (it emits no OTel — state-file channel only) | collector.py |
| 2.3 | Add the descriptor↔emission **parity test** (shared with AI-agent REQ-AAO-012) so declared attrs ⊆ emitted attrs — closing the C-3 drift risk | tests/ |

**Validation:** parity test passes (and fails on a deliberately mis-declared attr); project spans
appear in `generate_manifest()` output with category/orientation.

---

## Phase 3 — Document the ownership boundary (REQ-PRO-001, 004)

| Step | Change | Files |
|------|--------|-------|
| 3.1 | Add docstrings/comments stating the boundary: startd8 writes state files + spans + Kaizen JSON; **ContextCore owns** the gauges, **live progress computation**, and burndown dashboards | task_tracking_emitter.py, integrations/contextcore.py |
| 3.2 | Confirm the generator reports declared `contextcore_*` gauges as **ContextCore-owned honest-skip** (taxonomy REQ-OAT-011), not startd8-emitted | (cross-ref taxonomy generator) |

**Validation:** docs/comments present; no code reaches into ContextCore beyond the optional wrapper;
no progress-delta emitter is added (REQ-PRO-004 explicitly avoids it).

---

## Phase 4 — Declare delivery signals + SLIs (hand-authored) (REQ-PRO-003a, 006, 007)

The collector auto-discovers descriptors; SLO/alert/JSON-schema sections are **hand-maintained**.

| Step | Change | Files |
|------|--------|-------|
| 4.1 | Author a manifest section declaring the JSON delivery signals' schema (Kaizen `root_cause`/`pipeline_stage`/dual-score, velocity/trend, persistent-failure, improvement deltas) + sample SLI/PromQL query forms (REQ-PRO-003a/007) | observability/manifest.py (authored section) |
| 4.2 | Document generate-vs-cede: startd8 provides catalog + SLI defs + MAY emit delivery-health **alerts** (persistent-failure, quality-regression, cost-outlier) from owned signals; **dashboards are ceded** (REQ-PRO-006) | manifest.py / generator notes |

**Validation:** the manifest lists every delivery signal (no silent JSON-only project-health signal);
SLI query forms present; cede documented.

---

## Phase 5 — Deferred

- **REQ-PRO-003b (metric-ify):** emitting Kaizen/velocity as live OTel metrics — deferred (requires
  re-architecting post-run Kaizen into in-process instrumentation). L.
- **Live progress deltas:** owned by ContextCore — not built here (REQ-PRO-004).
- **C-5 (three quality scorers consolidation):** larger separate effort — flagged, not folded in.

---

## Traceability (requirement → phase)

| REQ-PRO | Phase | REQ-PRO | Phase |
|---------|-------|---------|-------|
| 001 | 3.1 | 005 | 1.1 |
| 002 | 1.1 + 2 | 006 | 4.2 |
| 003a | 4.1 | 007 | 4.1 |
| 003b (deferred) | 5 | 008 | 0.1 |
| 004 | 3.1 (document; no emitter) | — | — |

## Before-code checklist

- [ ] Every v0.2 requirement maps to a phase; every step traces to a requirement / Appendix-C item.
- [ ] Phase-1 descriptor-schema change is **shared** with the AI-agent plan (landed once).
- [ ] Parity test (2.3) is shared with AI-agent REQ-AAO-012 — one test mechanism, both categories.
- [ ] `task_tracking_emitter` stays OUT of the OTel collector (it's a state-file channel).
- [ ] No progress-delta emitter is built (REQ-PRO-004 ownership).
- [ ] Phase 0 net-removes lines (dead histogram, namespace cleanup).

---

*Plan v0.1 — paired with requirements v0.2. Category-4 is mostly documentation + declaring existing
spans in the shared descriptor manifest; the schema keystone + parity test are shared with the
AI-agent doc (land once). Metrics + live progress are deferred / ContextCore-owned. Net: small,
mostly declarative + cleanup.*
```

---

## Document Under Review: Requirements

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-obs-gap/docs/design/OBSERVABILITY_PROJECT_REQUIREMENTS.md`  ·  **Size:** 298 lines · 2803 words

```markdown
# Project Observability — Requirements (Taxonomy Category 4)

**Date:** 2026-05-31
**Status:** Draft v0.2 — post-planning self-reflective update (requirements only; no code this pass)
**Lineage:** Instantiates **Category 4 — Project Observability** of
`OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md` (the "reserved — signals emitted, no generator"
row). Evidence base: a read-only telemetry inventory of `src/startd8/` (task_tracking_emitter,
integrations/contextcore, otel_conventions, complexity/, improvement_tracking, contractors/
prime_postmortem + batch_postmortem, observability/manifest + collector).
**Subject observed:** the **project's development lifecycle** — task progress/status, hierarchy,
phase execution, complexity/blast-radius, delivery & output quality, velocity.

---

## 0. Planning Insights (self-reflective update, v0.1 → v0.2)

> A planning pass traced the startd8↔ContextCore seam, the descriptor manifest, and the JSON
> delivery-signal emission paths. Headline: **the ownership seam is already clean in code** —
> ContextCore is an *optional* import (graceful `_enabled=False` if absent); startd8 writes state
> files, ContextCore reads them. So the category-4 work is mostly **documentation + descriptor
> declaration**, not decoupling. Two requirements were over-optimistic and are corrected.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| REQ-PRO-001: boundary needs drawing (maybe code) | Code seam is **already clean** — ContextCore optional-import + file-consumer pattern, no hard dep, no bidirectional coupling | 001 = **pure documentation** (S): mirror the boundary in code comments; the doc was ~95% right |
| REQ-PRO-002: add `task_tracking_emitter` to the OTel descriptor manifest | `task_tracking_emitter` emits **no OTel** — only JSON state files (a *separate channel* to ContextCore). The real descriptor gap is the **`phase.*`/`task.*` OTel SPANS** (artisan runners + `development.py`) that ARE emitted but not declared | 002 **refined**: declare the *spans*; the state-file emitter stays out of the OTel manifest (it has no OTel) |
| REQ-PRO-003: surface delivery signals (implied metric-ify) | Kaizen/improvement/velocity are **post-run async JSON** (postmortem runs in a thread after the run); no inline emit point — metric-ifying needs re-architecture | 003 **split**: *declare-only* (manifest schema + sample SLI queries) is S and in scope; *metric emission* is L and deferred (resolves OQ-1 → declare-only) |
| REQ-PRO-004: startd8 emits live progress deltas | `task_tracking_emitter` is a **one-time** emitter; `percent_complete` is structurally **always 0** from startd8 (zero-point seed only). Live progress is computed by ContextCore from the state files | 004 **reframed**: progress is **ContextCore-owned**; startd8 emits only the seed. Do **not** build a delta emitter (wrong-owner accidental complexity). Resolves OQ-2 → ContextCore |
| (not in v0.1) | "**task**" names two different things: the **work-item** hierarchy (epic/story/task in `task_tracking_emitter`, state files) vs **codegen `task.*` span attributes** (`development.py` chunk attrs: complexity_tier/blast_radius) — a naming collision | **NEW REQ-PRO-008**: disambiguate the two "task" concepts in `otel_conventions.py` + descriptors |
| (not in v0.1) | The descriptor-schema change (add `category`/`orientation`) is the **same** change the AI-agent doc needs — one keystone serving cats 4 **and** 5 (and the taxonomy's declare-don't-guess) | **Convergence**: the `_OTEL_DESCRIPTORS` manifest is the **shared spine**; REQ-PRO-002/005 reference the AAO schema change, not duplicate it |
| (not in v0.1) | **Three overlapping quality scorers**: ImprovementTracker (6-cat doc quality), Kaizen RootCause (16×9), `query_security_score` — no unified quality taxonomy; and `complexity/classifier.py` creates an OTel histogram it **never records to** (dead) | Catalogued in Appendix C; the dead histogram is a quick win |

**Resolved open questions:**
- **OQ-1 → declare-only.** Delivery signals are post-run JSON; declare their schema + SLI queries in
  the manifest now; defer metric emission (REQ-PRO-003).
- **OQ-2 → ContextCore owns progress.** startd8 seeds the zero-point; ContextCore computes deltas
  (REQ-PRO-004).
- **OQ-3 → externally owned.** `install_completeness_percent` is produced by ContextCore / the
  cap-dev-pipe installer, not startd8 — ceded regardless of which category it lands in.

*Essential complexity: declare the existing project spans (with category/orientation) in the one
shared descriptor manifest + draw the (already-clean) ownership boundary in docs. The rest
(metric-ifying post-run JSON, live progress deltas) is either deferred or the wrong owner.*

---

## 0.1 Motivation

The SDK already produces a substantial body of *development-lifecycle* telemetry — task state,
phase/task spans, complexity signals, and rich delivery-quality data (Kaizen, improvement deltas,
batch velocity). But it accreted as internal pipeline instrumentation and, crucially, **ownership
is split** with ContextCore in a way nothing documents.

**The defining finding (vs Category 5):** the category-4 *metrics* the run-007 onboarding metadata
declared — `contextcore_task_progress`, `contextcore_task_status`,
`contextcore_install_completeness_percent` — are **NOT emitted by startd8**. They are **owned by
ContextCore** (the external `TaskTracker`). startd8's contribution is the **raw lifecycle signals**
(task **state files**, OTel **spans**, Kaizen/velocity **JSON**) that ContextCore and the
`/context-core-tracker` + `/time-series-progress-tracker` skills consume to produce those gauges and
the burndown/velocity dashboards. Category 4 is therefore a **shared, split-ownership** category —
unlike Category 5, where the SDK emits its own metrics directly.

This document surfaces what the SDK produces, draws the startd8↔ContextCore boundary explicitly, and
names the gaps (rich signals stuck in JSON, span conventions absent from the descriptor manifest, no
live progress deltas).

This is a **requirements** document. Code alignment is a separate, follow-up pass.

---

## 1. What we already collect (the evidence base)

### 1.1 Task lifecycle — state files + zero-point events (startd8 produces ✅, ContextCore consumes)

`workflows/builtin/task_tracking_emitter.py` (`emit_task_tracking_artifacts()`) writes **SpanState
v2** task state files + an NDJSON event log, installable to `~/.contextcore/state/{project_id}/`:
- hierarchy **epic → story → task** via `parent_span_id`;
- per-task attributes: `task.{id,title,type,status,priority,story_points,depends_on,labels,
  feature_id,target_files,estimated_loc}`, `project.id`, `sprint.id`;
- **zero-point** `task.created` event with `percent_complete: 0` (burndown seed).

**Owner:** startd8 produces the files; **ContextCore** consumes them and owns the metric-ified
`task.status`/progress.

### 1.2 Phase & task OTel spans (startd8 emits ✅ via OTLP → Tempo)

`otel_conventions.py` defines the conventions; `contractors/artisan_contractor.py` +
`artisan_phases/runner.py` emit them:
- `phase.{type}.attempt.{n}` — `phase.{name,status,cost,duration_seconds}`;
- task spans — `task.{id,title,domain,phase,status,cost,attempts,complexity_tier,blast_radius}`.

### 1.3 Complexity / scope (startd8 emits ✅ as span attributes)

- `task.complexity_tier` (SIMPLE/MODERATE/COMPLEX) — `complexity/classifier.py`;
- `task.blast_radius` (caller count, threshold tier-3 ≥5) — `complexity/signals.py`.

### 1.4 Delivery & output quality (startd8 produces ✅ — but JSON/YAML, **not** metrics)

- **Improvement tracking** (`improvement_tracking.py`): per-version document-quality deltas across 6
  categories (Completeness, Clarity, Consistency, Testability, Maintainability, DX) →
  `project-index-local.yaml`.
- **Kaizen / post-mortem** (`contractors/prime_postmortem.py`): `root_cause` (16-value enum),
  `pipeline_stage`, dual scoring (PASS ≥0.8 / PARTIAL / FAIL <0.4), cost-outlier + cross-feature
  pattern detection, `query_security_score` → `kaizen-metrics.json`, `prime-postmortem-report.json`,
  `kaizen-suggestions.json`.
- **Batch velocity** (`contractors/batch_postmortem.py`): `tasks_per_run_avg`, `trend`
  (stable/accelerating/decelerating), `estimated_runs_remaining`, persistent-failure tracking
  (same task failing across ≥2 runs) → JSON ledger.

### 1.5 The `contextcore_task_*` gauges — **ContextCore-owned, not SDK-emitted** ❌

`contextcore_task_progress`, `contextcore_task_status`, `contextcore_install_completeness_percent`
appear only in metadata/test declarations; **no emission site exists in startd8**. ContextCore's
`TaskTracker` produces them from the §1.1 state files.

### 1.6 Descriptor-manifest status (gap ❌)

Unlike cost/session metrics, the project-obs **`task.*`/`phase.*` conventions are declared in
`otel_conventions.py` prose but NOT in any module's `_OTEL_DESCRIPTORS`**, and
`task_tracking_emitter` is absent from `observability/collector.py`'s `_INSTRUMENTED_MODULES`. So
project signals are **not in the descriptor catalog** that drives the taxonomy generator.

---

## 2. Findings

| # | Finding | Evidence |
|---|---------|----------|
| PRO-D1 | **Split ownership undocumented.** SDK produces raw signals (state files, spans, Kaizen JSON); ContextCore owns the metric gauges + burndown dashboards. Nothing draws the line | §1.1/1.5 |
| PRO-D2 | **Declared-not-emitted gauges.** `contextcore_task_*` are declared in onboarding metadata but not emitted by startd8 — a category-4 analogue of the `capability_index` cede | §1.5 |
| PRO-D3 | **Rich delivery signals stuck in JSON.** Improvement deltas, Kaizen root-cause/scores, batch velocity are valuable project-health signals but are JSON/YAML only — not observable via metrics/dashboards | §1.4 |
| PRO-D4 | **Span conventions absent from the descriptor manifest.** `task.*`/`phase.*` are prose-declared, not in `_OTEL_DESCRIPTORS`; the generator can't see them | §1.6 |
| PRO-D5 | **No live progress deltas.** `percent_complete` is seeded at 0 but no `task.updated` events are emitted during execution — progress is point-in-time, not live (burndown can't move from SDK signals alone) | §1.1 |
| PRO-D6 | **Burndown/velocity dashboards are external.** Realized by ContextCore + the `/context-core-tracker` / `/time-series-progress-tracker` skills, not generated by startd8 | §6 inventory |

---

## 3. Requirements

### 3.1 Draw the ownership boundary

**REQ-PRO-001 (ownership boundary — documentation; seam already clean).** Planning confirmed the
code seam is already clean (ContextCore is an optional import with graceful degradation; startd8
writes state files that ContextCore reads — no hard dependency, no bidirectional coupling). So this
is a **documentation** requirement, not a decoupling one: the boundary MUST be stated in the docs
and mirrored in code comments (on `task_tracking_emitter.emit_task_tracking_artifacts()` and
`contextcore.py`'s `TaskTrackerWrapper`):
- **startd8 produces** the raw lifecycle signals — task **state files** (SpanState v2), phase/task
  **OTel spans**, complexity span attributes, and Kaizen/improvement/velocity **JSON artifacts**.
- **ContextCore owns** the metric-ified gauges (`contextcore_task_progress`/`status`/
  `install_completeness_percent`), the **live progress computation** (the deltas off the seeded
  zero-point — REQ-PRO-004), and the burndown/velocity dashboards.
The observability artifact generator MUST NOT claim startd8 emits the `contextcore_*` gauges; where
declared, they are reported as **ContextCore-owned** (honest-skip, mirroring the taxonomy's
`capability_index` cede, REQ-OAT-011).

### 3.2 Close the descriptor-manifest gap

**REQ-PRO-002 (declare the project SPANS, PRO-D4 — refined).** The `phase.*` and codegen `task.*`
span attributes that are **already emitted** (by `artisan_phases/runner.py`, `artisan_contractor.py`,
`development.py`) MUST be declared in `_OTEL_DESCRIPTORS` with `category = project_observability`
and `orientation = system`, and those emitting modules added to `collector.py`'s
`_INSTRUMENTED_MODULES`, so the project spans enter the descriptor catalog that feeds generation
(same loop as AI-agent REQ-AAO-008). **Scope correction (planning):** this covers the OTel **spans**
only — `task_tracking_emitter` emits **no OTel** (it writes JSON state files on a *separate* channel
to ContextCore) and MUST **not** be added to the OTel manifest. The `category`/`orientation` schema
fields are the **same** addition the AI-agent doc specifies (REQ-AAO-004) — this requirement
**reuses** that single shared schema change (the descriptor manifest is the shared spine for
categories 4 & 5), it does not duplicate it.

### 3.3 Surface the delivery-quality signals

**REQ-PRO-003 (make delivery quality discoverable — declare-only now; metric-ify deferred).**
Planning found these signals (Kaizen `root_cause`/`pipeline_stage`/dual-score, velocity/trend,
persistent-failure, quality-improvement deltas) are **post-run async JSON** (postmortem runs in a
thread after the run) with no inline emit point. So the requirement splits:
- **REQ-PRO-003a (declare-only — in scope, S):** these signals MUST be **declared in the manifest**
  (their JSON schema + sample SLI/PromQL query forms) as a hand-authored section, so the catalog has
  no silent JSON-only project-health signals and the generator can reference them.
- **REQ-PRO-003b (metric emission — deferred, L):** emitting them as live OTel metrics is deferred —
  it requires re-architecting Kaizen from post-run analysis into in-process instrumentation, which is
  out of scope for this pass.

(Resolves OQ-1: declare-only.) Note: the collector auto-discovers descriptors but **SLO/alert/JSON-schema
sections are hand-maintained** — so REQ-PRO-003a and REQ-PRO-007 are authored sections, not
auto-generated.

### 3.4 Live progress (optional/phased)

**REQ-PRO-004 (progress ownership — reframed: ContextCore, not startd8).** Planning showed
`task_tracking_emitter` is a **one-time** emitter and `percent_complete` is structurally **always 0**
from startd8 (a zero-point seed). Building a `task.updated` delta emitter in startd8 would put
progress computation in the **wrong owner** and add accidental complexity. The requirement is
therefore to **document that live progress is ContextCore-owned** — startd8 provides the seeded
zero-point; ContextCore computes the deltas from the state files + run telemetry. startd8 MUST NOT
build a progress-delta emitter. (Resolves OQ-2.)

### 3.5 Orientation & artifacts

**REQ-PRO-005 (orientation).** Project-obs artifacts classify on the orientation axis: burndown /
velocity / quality dashboards = **human**; task/phase spans, SLI definitions, descriptor catalog =
**system**; delivery-health alerts (persistent-failure, quality-regression, cost-outlier) =
**bridge**.

**REQ-PRO-006 (artifacts startd8 generates vs cedes).** Like Category 5, startd8 provides the
**signal catalog + SLI/alert definitions**; the **burndown/velocity dashboards** are **ceded** to
ContextCore + the tracker skills (cross-referenced, not generated here). startd8 MAY generate
**delivery-health alerts** from its own Kaizen/batch signals (persistent-failure, quality-regression,
cost-outlier) since it owns those signals.

**REQ-PRO-007 (project SLIs/SLOs — system).** Definable from owned signals: delivery success rate
(`tasks_passed / tasks_attempted`), velocity trend, quality-improvement trend, blast-radius
distribution, persistent-failure count (objective: 0). These are **hand-authored** manifest sections
(the collector auto-discovers descriptors, not SLI/SLO templates — see REQ-PRO-003).

**REQ-PRO-008 (disambiguate the two "task" concepts — from planning).** The token "task" denotes two
distinct things and the requirements/code MUST disambiguate them, or routing and dashboards conflate
them:
- **work-item task** — the epic/story/**task** hierarchy in `task_tracking_emitter` (state files,
  ContextCore-bound; the burndown unit);
- **codegen task** — the `task.*` span attributes in `development.py`/`otel_conventions.py`
  (per-chunk codegen: `complexity_tier`, `blast_radius`, `attempts`, `cost`).
The descriptor declarations (REQ-PRO-002) and `otel_conventions.py` MUST name these distinctly (e.g.
`workitem.*` vs `codegen.task.*`) so the manifest, SLIs, and any generated artifacts don't merge a
plan's work-items with code-generation chunk telemetry.

---

## 4. Non-requirements / out of scope

- Implementing the category-4 **generator** (taxonomy REQ-OAT-041 reserves the namespace).
- Re-implementing ContextCore's gauges or burndown/velocity dashboards — those are **ceded**
  (REQ-PRO-001/006).
- Category-5 (agent) and category-1 (service) signals — separately specified.

## 5. Open questions

- **OQ-1.** Which delivery signals (REQ-PRO-003) warrant metric emission vs descriptor-declare-only?
  (Kaizen root-cause distribution and velocity are the strongest dashboard candidates.)
- **OQ-2.** Should live progress deltas (REQ-PRO-004) be startd8's job at all, or strictly
  ContextCore's once it consumes the state files? (Boundary question — ties to REQ-PRO-001.)
- **OQ-3.** Is `install_completeness_percent` project-obs (delivery) or pipeline-innate (capdevpipe
  install bookkeeping)? Its emission owner (ContextCore vs cap-dev-pipe installer) decides.

---

## Appendix A — signal → (owner, orientation, surfaced?) catalog

| Signal | Kind | Owner | Orientation (of artifacts) | Surfaced today? |
|--------|------|-------|----------------------------|-----------------|
| task state files (SpanState v2) | state file | startd8 → ContextCore | system | ✅ ~/.contextcore/state/ |
| `task.created` / `percent_complete:0` | event | startd8 | human (burndown) | ✅ state files (no live delta) |
| `phase.{name,status,cost,duration}` | span | startd8 | system | ✅ OTLP/Tempo (not in descriptors — PRO-D4) |
| `task.{complexity_tier,blast_radius}` | span attr | startd8 | system / human | ✅ OTLP (not in descriptors) |
| improvement deltas (6 categories) | YAML | startd8 | human | ❌ project-index JSON only |
| Kaizen `root_cause`/`pipeline_stage`/dual-score | JSON | startd8 | bridge (alert) / human | ❌ kaizen-metrics.json only |
| batch velocity / persistent-failure | JSON | startd8 | human / bridge | ❌ ledger only |
| `contextcore_task_progress/status` | gauge | **ContextCore** | human / bridge | ❌ external (ceded) |
| `install_completeness_percent` | gauge | ContextCore / capdevpipe | — | ❌ external (OQ-3) |

## Appendix B — requirement index

`REQ-PRO-001` ownership boundary · `REQ-PRO-002` descriptor-manifest (declare spans) ·
`REQ-PRO-003` surface delivery quality · `REQ-PRO-004` live progress (phased) · `REQ-PRO-005`
orientation · `REQ-PRO-006` generate-vs-cede · `REQ-PRO-007` project SLIs.

---

*(v0.1 footer superseded by the v0.2 summary below.)*

## Appendix C — pre-existing accidental complexity to eliminate (opportunistic)

Catalogued by the planning pass; the code-alignment follow-up SHOULD remove these. Effort S/M/L.

| # | Smell | Location | Why accidental | Distillation | Effort |
|---|-------|----------|----------------|--------------|--------|
| C-1 | **"task" naming collision** | `otel_conventions.py`, `task_tracking_emitter.py`, `development.py` | work-item task vs codegen-chunk `task.*` attrs share the name | disambiguate (`workitem.*` vs `codegen.task.*`) (REQ-PRO-008) | S |
| C-2 | **Dead OTel histogram** | `complexity/classifier.py:23–35` | creates a tier histogram but **never records** to it | remove, or actually `record()` tier classifications | S |
| C-3 | **Constants declared but call-sites use raw strings** | `otel_conventions.py` (AttributeKeys) vs `development.py:5327`, `runner.py:525` | span-attr names defined as constants but set via literal strings → drift | use the constants everywhere; a parity check ties declared↔emitted | M |
| C-4 | **Span-name pattern mismatch** | `artisan_contractor.py` (`artisan.workflow.{id}.phase.{phase}`) vs `runner.py` (`phase.{type}.attempt.{n}`) | two patterns for phase spans; unclear if same hierarchy | reconcile/​document the phase-span hierarchy | S |
| C-5 | **Three overlapping quality scorers** | `improvement_tracking.py` (6-cat doc quality) · Kaizen `prime_postmortem.py` (16 root-cause × 9 stage) · `query_prime/kaizen_metrics.py` (`query_security_score`) | three independent quality taxonomies, no unifying model | document the three lenses; a unified quality signal hierarchy is a *separate, larger* effort (flag, don't fold in) | L (deferred) |
| C-6 | **SpanState v2 schema duplicated** across producer + external consumer | `task_tracking_emitter._build_state_file()` hardcodes the schema ContextCore also depends on | the contract lives in two repos with no shared definition | document the schema-version contract explicitly (a shared dataclass is hard across the repo boundary) | M |
| C-7 | **Descriptor schema lacks category/orientation** | `observability/manifest.py` | the routing fields cats 4 & 5 need aren't in the schema | add two fields — **shared** with AI-agent REQ-AAO-004 (one change, two categories) | S |

**Net:** C-1/C-2/C-7 are S quick wins (C-7 is shared with the AI-agent doc — one change). C-3/C-4/C-6
are M documentation/parity tidy-ups. C-5 (three quality scorers) is real but **larger scope** — flagged
for a separate consolidation, not folded into this pass to avoid scope creep.

---

*v0.2 — Post-planning self-reflective update. Confirmed the ownership seam is already clean (001 →
documentation), refined 002 (spans not state-files; reuses the shared descriptor-schema change),
split 003 (declare-only in scope / metric-ify deferred — Kaizen is post-run async), reframed 004
(progress is ContextCore-owned; don't build a delta emitter), added 008 (disambiguate the two "task"
concepts), resolved 3 open questions, and catalogued 7 accidental-complexity items (Appendix C). Net
finding: category-4 is mostly documentation + declaring existing spans in the one shared descriptor
manifest — the boundary is clean and the heavy lifting (metrics, progress) is deferred or
ContextCore's.*
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
