# Convergent Review Prompt

**Generated:** 2026-06-12 18:20:27 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 2 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 12 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/view-prose/VIEW_PROSE_FOLLOWTHROUGH_PLAN_v0.1.md` | 163 lines · 1939 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/view-prose/VIEW_PROSE_FOLLOWTHROUGH_REQUIREMENTS_v0.1.md` | 340 lines · 3496 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/private/tmp/followthrough_crp_focus.md` | 11 lines · 286 words |

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
| Max suggestions (soft cap) | 12 |
| Review areas to consider | Architecture, Interfaces, Data, Risks, Validation, Ops, Security |

### Sponsor / author — review focus (from --focus-file)

Prioritize the following when scoring severity and ordering work. Do not treat this file as normative over the requirements or plan; use it to **weight** attention.

## Where reviewer input is most valuable

1. **Group A — KIND_TO_INPUTS single source of truth (FR-DRC-1) + regression lock across 5 providers (FR-DRC-5).** Is one declarative kind→manifest map actually achievable when the 5 deterministic providers recognize files differently (backend by embedded `kind`; view/scaffold/polish by marker or path-suffix; frontend TS-side)? Does the lock have a reliable way to ENUMERATE every owned kind, or are some kinds only discoverable at render time? What's the failure mode if a provider owns a kind absent from the map?

2. **Group A — skip-hook threading correctness (FR-DRC-3).** Wiring the unused `_read_anchored` helpers into `owned_file_in_sync` changes the skip-hook's behavior for EXISTING apps: files that today falsely $0-skip will now correctly re-check and may flip to "not in-sync" → fall to LLM. Is that a desirable correctness fix or a surprising cost/behavior change for downstream apps mid-flight? Should it be staged/flagged?

3. **Group G — ingestion ordering (OQ-6) + Empty-state semantics (FR-VCE-2).** `parse_view_prose(known_views=...)` needs views extracted first. Is there a dependency/ordering risk in `extract.py`'s candidate loop? And `Empty state:` is authored per-view but `empty` is only valid on model-scoped detail-compose — what happens to `Empty state:` authored on a dashboard/board/import-flow view (today silently dropped; after FR-VCE-2 it must NOT start loud-failing existing reqs docs)? Back-compat risk.

4. **Group G — manifest-extraction parity 6/8→8/8 (FR-VCE-4 display.yaml).** Is deriving display.yaml (structure/bindings) from the reqs doc actually feasible, or does it need richer authoring than the doc carries (FK label resolution, column order)? Could be a much bigger lift than view_prose extraction — scope risk.

5. **Cross-cutting — should Group A be carved into its own requirements doc/PR (OQ-1)?** It's a pre-existing correctness fix with a different risk profile than the additive Group G/D/C work.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/view-prose/VIEW_PROSE_FOLLOWTHROUGH_PLAN_v0.1.md`  ·  **Size:** 163 lines · 1939 words

```markdown
# View Prose Follow-Through — Implementation Plan (reflective loop Phase 2)

**Version:** v0.1 (post-exploration; feeds the v0.2 reflective update of the requirements)
**Date:** 2026-06-12
**Status:** Plan — ready to reflect back onto the requirements
**Pairs with (the "what"):** `VIEW_PROSE_FOLLOWTHROUGH_REQUIREMENTS_v0.1.md` (18 FRs across groups A-F).
All citations are from a read of SDK `main` @ `0e8d08fb`.

> **Reading order.** §0 is the discoveries that change the requirements (the centerpiece — the loop
> working). §1 is the per-group implementation shape (file:line-grounded). §2 is the reshaped
> scope/sequencing. §3 is what flows back to v0.2.

---

## 0. Discoveries (what planning revealed — these reshape the requirements)

| # | The requirements assumed (v0.1) | Planning revealed | Impact |
|---|---|---|---|
| **D1** | FR-FMT-1 is "add a View-copy section to the template" — a docs edit | **The requirements doc is a deterministic ($0, no-LLM) manifest SOURCE.** `manifest_extraction/extract.py` ingests it and emits **6 manifests** (pages/app/ai_passes/human_inputs/views/completeness) + schema — but **NOT `view_prose.yaml`** (and not `display.yaml`). The consumer (`parse_view_prose`) exists; the **producer (extractor) does not** — the SDK is half-wired. | **FR-FMT-1 is PROMOTED** from a doc edit to a real codegen capability: *author view copy in the reqs doc → deterministically generate `view_prose.yaml`*. Becomes its own FR group (G). |
| **D2** | (not seen) | **`Empty state:` is ALREADY authored** in every `### View:` block of the template, but `parse_views` has no home for it → it maps to **`not_extracted(generator-gap)`** (`extractors.py:241-245`, `KICKOFF_AUTHORING_CONTRACT.md:171`). Meanwhile view_prose's `empty` key + renderer now exist. | **NEW quick win, invisible before planning:** connect the existing-but-ignored `Empty state:` authoring → `view_prose.yaml` `empty:`. Both ends already exist; only the extractor connects them. |
| **D3** | (not seen) | **The extraction emits 6 of the 8 manifests the cascade consumes** — `view_prose.yaml` AND `display.yaml` are both un-derived (same gap class). | New theme: **manifest-extraction parity** — the derivation should produce every manifest the $0 cascade reads. display.yaml is a sibling of the view_prose extraction. |
| **D4** | Group A "skip-hook threading" needs building | The backend provider **already has** `_read_anchored()` / `_read_manifest()` / `_read_human_inputs()` helpers — **but `is_in_sync()` doesn't call them** (passes schema only, `provider.py:29-35`). `check_drift` already has the full kind-routing + signature. | **FR-DRC-3 is smaller than feared** — "wire up helpers that already exist," not new plumbing. Strengthens the "small thread-through" verdict. |
| **D5** | FR-DRC-2 = "add flow kinds to `_FORMS_KINDS`" | Flow kinds (`fastapi-flow`/`flow-shell`) are in **no** kind-set AND **no** renderer map; a kind needs **both** to be drift-checkable. Flows are semantically distinct from forms post-create. | FR-DRC-2 reframed as a **new `_FLOWS_KINDS` family** (kind-set + `_check_flows_drift` + `_flows_renderers`), parallel to forms — slightly bigger but cleaner than overloading `_FORMS_KINDS`. |
| **D6** | FR-DRC-5 regression lock spans the backend kinds | There are **5 deterministic providers** (backend kind-routed; frontend/scaffold/polish marker-or-path; view path-suffix). The lock must span **all** of them. The implicit kind→inputs map (the `_*_KINDS` sets) made **explicit** (FR-DRC-1's `KIND_TO_INPUTS`) is what makes both the skip-hook threading AND the lock possible. | FR-DRC-1 is **load-bearing for 3/5** (not optional); FR-DRC-5 widened to all providers. |
| **D7** | FR-FMT-2 (codify the reflective lifecycle) might be a parser concern | **Zero** machine consumption — `manifest_extraction/*` + `grammar.py` have **no** refs to "Appendix"/"Planning Insights"/"version lineage"/"what changed"; format rule 5 ignores any non-anchored section. | **FR-FMT-2 NARROWS** to a pure format-doc edit (human convention) — lower risk, fully decoupled from FR-FMT-1. |
| **D8** | FR-DP-2 = extract a shared untracked-fragment primitive | The three mechanisms are **intentionally divergent**: pages/view-prose are **generate-time** untracked fragments; **AI prompts are RUNTIME-loaded** (read from disk by the generated harness, not a generate-time fragment at all — `ai_layer.py:695-700`). Timing/format/discovery all differ. | **FR-DP-2 DROPPED** (extraction not worth it / partly impossible — AI-prompt isn't the same pattern). Folds into FR-DP-1 as "document the pattern + note the runtime-binding variant." |
| **D9** | FR-WCI-2 (content-completeness rollup) is a quick win bundled with FR-WCI-1 | FR-WCI-1 (add view_prose to the catalog + per-view chrome status) **is** quick — the `Status` model + `_yaml_state` pattern exist (`plan.py:45-50`). But the **rollup** has no existing per-surface aggregation; it needs a new `ContentCoverageStats` + a `--json` schema bump = **MEDIUM**. | **Split FR-WCI-1 (quick) from FR-WCI-2 (medium).** |

**Net:** > a third of the v0.1 FRs are materially reshaped — the loop working as intended. The single
biggest shift: the "template/format" bucket is not cosmetic — the reqs doc is a deterministic manifest
*compiler*, and its two newest target manifests aren't compiled yet. That converts FR-FMT-1 into a
high-value capability with an **immediate payoff** (the already-authored `Empty state:` dead-end lights up).

---

## 1. Implementation shape (per group, file:line-grounded)

### Group A — Drift-recognition completeness (the small thread-through)
- **FR-DRC-1 — explicit `KIND_TO_INPUTS`.** Add a module-level dict in `backend_codegen/drift.py` mapping
  each owned kind → its required manifest names (`schema` always; `+forms` for `_FORMS_KINDS`; `+pages`
  for `_PAGES_KINDS`; `+ai_passes,+human_inputs` for `_AI_KINDS`; `+forms` for the new `_FLOWS_KINDS`;
  `schema`-only for `_renderers()` kinds + `_SETTINGS_KINDS`). The implicit map is the `_*_KINDS` sets
  (`drift.py:47-74`); this makes it explicit + testable. **Load-bearing for FR-DRC-3 and FR-DRC-5.**
- **FR-DRC-2 — `_FLOWS_KINDS` family.** New `_FLOWS_KINDS = {"fastapi-flow","flow-shell"}` + a
  `_flows_renderers()` (`render_flow_router`/`render_flow_shell` from `flow_generator.py:30/112`) +
  `_check_flows_drift()` (forms-hash style: schema + views.yaml), routed in `check_drift` (`drift.py:539`).
- **FR-DRC-3 — backend `is_in_sync` threads the kind's manifests.** In `backend_codegen/provider.py`,
  `is_in_sync` reads the file's kind (`embedded_artifact_kind`), looks up `KIND_TO_INPUTS`, resolves only
  those manifests via the **existing** `_read_anchored()`/`_read_manifest()`/`_read_human_inputs()`
  (`provider.py:62-101`, currently unused), and `owned_file_in_sync` gains the manifest kwargs to forward
  to `check_drift` — mirroring the CLI (`cli_generate.py:280-290`). **No new plumbing.**
- **FR-DRC-4 — view provider threads `display_text`.** `view_codegen/provider.py:25-37` resolves
  `view_prose.yaml` but not `display.yaml`; add a `_read(suffix="display.yaml", …)` and pass `display_text`
  to `views_in_sync` (which already accepts it). ~3 lines.
- **FR-DRC-5 — regression lock across all 5 providers.** A test enumerates every owned kind (backend
  `_*_KINDS` + the `_renderers()` keys; the view/scaffold/polish/frontend providers' kinds) and asserts the
  skip-hook resolves the inputs `KIND_TO_INPUTS` declares. Fails when a future kind is added without wiring.

### Group G — View-copy extraction (the promoted FR-FMT-1; D1/D2/D3)
- **FR-VCE-1 — `extract_view_prose()`.** New extractor in `manifest_extraction/extractors.py` parsing
  per-view copy keys from each `### View:` block (the block already uses the `- Key: value` grammar,
  `grammar.py:129`). Wire into the candidate set (`extract.py:145-158`) and the round-trip table
  (`extract.py:162-175`) calling the **existing** `parse_view_prose(text, known_views=…)`
  (`view_prose.py:59`) so a bad copy block fails loudly at *ingestion* (FR-WPI-4), not at `generate views`.
- **FR-VCE-2 — close the `Empty state:` dead-end (the quick win, D2).** Map the already-authored
  `Empty state:` line (`extractors.py:241-245`, today `not_extracted(generator-gap)`) to `view_prose.yaml`
  `empty:` for model-scoped detail-compose views. Existing authoring → existing renderer; only the extractor
  is new.
- **FR-VCE-3 — per-archetype controlled grammar.** The extractor parses `title`/`intro` (any HTML view),
  `empty` (detail-compose model), `success`/`error`/`controls` (import-flow) — and the **existing renderer
  already rejects archetype-invalid combinations** (`renderers.py:1862-1881`), so validity is enforced
  end-to-end with no new validator.
- **FR-VCE-4 (sibling, D3) — `display.yaml` extraction parity.** The same gap exists for `display.yaml`
  (structure layer). Note it as a parallel item; may be its own increment. Brings the derivation to 8/8
  manifests.

### Group C — Format/template (mostly doc; D7)
- **FR-FMT-1' — the template "View copy" keys** (now the *authoring surface* for Group G): add the per-view
  copy keys to `REQUIREMENTS_TEMPLATE.md`'s `### View:` block + a `[consumed by: extraction →
  view_prose.yaml]` annotation in `REQUIREMENTS_AND_PLAN_FORMAT.md`. (Pairs with FR-VCE-1.)
- **FR-FMT-2 — reflective-loop conventions (pure doc, D7):** add §0 Planning Insights / Appendix A-B-C /
  "what changed" / version-lineage / Implementation-Reflections conventions to the format doc + template
  scaffolds. **No parser** touches these.
- **FR-FMT-3 — Words/Structure rule** + **FR-FMT-4 — `$0`-codegen AC checklist:** format-doc additions.

### Group D — Wireframe + capability index
- **FR-WCI-1 (quick).** Add `"view_prose": "prisma/view_prose.yaml"` to `wireframe/inputs.py:30-38`
  CONVENTION_PATHS; a `_view_prose_state()` parallel to `_yaml_state()`; extend `_views_section()`
  (`plan.py:586-636`) to emit per-view chrome status (authored/raw) using the existing `Status` model
  (`plan.py:45-50`).
- **FR-WCI-2 (medium, split out).** A `ContentCoverageStats` rollup (pages + view-copy + AI prompts) in
  `build_wireframe_plan()` + a `--json` `content_completeness` block (schema-version bump).
- **FR-WCI-3 (quick).** Two capability-index entries (`startd8.codegen.composite_views`,
  `startd8.codegen.view_prose`) matching the 12-field de-facto shape (`startd8.sdk.capabilities.yaml:611`).

### Group B — Assembly-inputs consistency (docs)
- **FR-KIN-1/2/3** — correct the stale `ASSEMBLY_INPUTS.md` view_prose entry; classify it under Words;
  add a template row. Pure docs.

### Group F — Design principle (D8)
- **FR-DP-1 — principle doc** (~2-3 pp, MOTTAINAI/HAYAI structure: principle → why → violations → rules →
  changelog) covering the **generate-time untracked-fragment** pattern (pages + view-prose), and noting
  AI-prompts as a **related runtime-binding variant** (not the same pattern).
- **~~FR-DP-2~~ — DROPPED.** Extraction not worth it (divergent timing/format/discovery; AI-prompt is
  runtime, not a generate-time fragment). Folds into FR-DP-1.

---

## 2. Reshaped scope & sequencing
1. **Group A** (drift-recognition) — small thread-through, fixes silent $0→LLM fallthrough + 3 verified
   bugs. Its own PR. *(FR-DRC-1 first; it unblocks 3+5.)*
2. **Group G** (view-copy extraction) — the high-value unlock; FR-VCE-2 (close `Empty state:`) is the
   cheapest first slice and proves the path. Pairs with FR-FMT-1'.
3. **Group D** (wireframe FR-WCI-1 + capability index FR-WCI-3) — quick wins.
4. **Group C/B/F** (docs) — cheap; FR-FMT-2/3/4, FR-KIN-*, FR-DP-1.
5. **FR-WCI-2** (rollup) + **FR-VCE-4** (display extraction parity) — medium follow-ups.

---

## 3. Reflection → what flows back to the requirements (v0.1 → v0.2)
- **Promote FR-FMT-1 → a new Group G (view-copy extraction)** and reframe the "template" bucket: the reqs
  doc is a deterministic manifest compiler; the win is *author copy → derive `view_prose.yaml` ($0)*.
- **Add the `Empty state:` quick win (FR-VCE-2)** — invisible before planning; both ends already exist.
- **Add the manifest-extraction-parity theme (FR-VCE-4 / display.yaml)** — the derivation emits 6 of 8.
- **Strengthen Group A** framing (plumbing already exists, unused) and reframe FR-DRC-2 as a `_FLOWS_KINDS`
  family; widen FR-DRC-5 to all providers; mark FR-DRC-1 load-bearing.
- **Narrow FR-FMT-2** to pure doc (no parser). **Drop FR-DP-2** (fold into FR-DP-1). **Split FR-WCI-1
  (quick) from FR-WCI-2 (medium).**

---

*v0.1 — Plan from `manifest_extraction/` + `backend_codegen/drift.py` + `wireframe/` exploration at
`0e8d08fb`. Central finding: the requirements doc is a deterministic ($0) manifest compiler that doesn't
yet compile `view_prose.yaml`/`display.yaml`, and an already-authored `Empty state:` field is a dead-end
the shipped view_prose machinery can now light up. Next: apply the §3 reflections to requirements v0.2.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/view-prose/VIEW_PROSE_FOLLOWTHROUGH_REQUIREMENTS_v0.1.md`  ·  **Size:** 340 lines · 3496 words

```markdown
# View Prose Follow-Through — Ecosystem Consistency, Drift-Recognition Completeness & Unlocked Enhancements — Requirements

**Version:** 0.2 (Post-planning — self-reflective update; reflective loop Phase 4)
**Date:** 2026-06-12 (v0.2, v0.1)
**Status:** Draft (post-planning; ready for CRP / implementation)
**Owner:** `startd8-sdk` (SDK-internal + kickoff templates) · touches consumer `strtd8` docs
**Pairs with:** `docs/design/view-prose/VIEW_PROSE_FOLLOWTHROUGH_PLAN_v0.1.md` (the planning pass whose
code-grounded findings drove this v0.2).
**Trigger:** the View Prose capability shipped to `main` 2026-06-12 (`0e8d08fb`; full key-set
title/intro/empty/success/error/controls). Building it (a) **proved** reusable patterns and (b)
**surfaced** that several ecosystem surfaces don't yet know `view_prose.yaml` exists, and that the
deterministic skip-hook silently drops manifest inputs.
**Related:** `docs/design/view-prose/VIEW_PROSE_PLAN_v0.1.md` (the shipped capability, v0.5),
`strtd8/docs/USER_FACING_CONTENT_REQUIREMENTS.md` (v0.9, the consumer contract),
`docs/design/kickoff/templates/REQUIREMENTS_TEMPLATE.md` + `REQUIREMENTS_AND_PLAN_FORMAT.md`,
`strtd8/docs/v2/ASSEMBLY_INPUTS.md`, the **editors-archetype** planning (which independently surfaced
drift bugs A-2/A-3 below; this doc consolidates them).
**SDK citations are `verify-at-home`** (drawn from a read of `main` at `0e8d08fb`).

---

## 0. Why this exists (the observed state)

Shipping View Prose was the SDK's *fourth* hash-exempt prose manifest (`pages.yaml`→`*.md`,
`ai_passes.yaml`→`*.md`, the parked `view_prose.yaml`, now live `view_prose.yaml`→fragments). Two things
became undeniable:

1. **The manifest ecosystem has a recognition hole.** The "$0 deterministic skip" thesis depends on the
   prime-contractor skip-hook recognizing a manifest-derived owned file as in-sync. But the skip-hook
   verifies with **schema only** — it drops every other manifest (`views.yaml`'s `forms:`, `pages.yaml`,
   `display.yaml`, `completeness.yaml`, `human_inputs.yaml`, `ai_passes.yaml`, and now `view_prose.yaml`).
   So manifest-derived owned files **fall through to the LLM** — paying cost and re-introducing
   non-determinism for files the SDK can generate for $0. View Prose adds *more* files to this fragile
   path, so it both **necessitates** and is partly **blocked** by the fix.

2. **The ecosystem doesn't know `view_prose.yaml` exists.** The assembly-inputs inventory describes the
   *overruled* design; the wireframe pre-gen readout omits view-copy coverage; the capability index has
   no entry; the kickoff requirements template has no place to declare view copy. Each is a small
   consistency debt that, left alone, drifts the docs from the shipped reality.

Separately, the build **proved** patterns worth elevating (a prose-gated additive-manifest principle) and
**unblocked** quick wins (the fragment mechanism now exists to absorb scattered hardcoded copy).

This doc groups the work into FR families. **Group A** (drift-recognition) is the architectural centerpiece;
**Group G** (view-copy extraction) is the highest *value* unlock — both surfaced/sharpened by the planning
pass below.

---

## 0.5 Planning Insights (self-reflective update, v0.1 → v0.2)

> The planning pass (`…_PLAN_v0.1.md`) read `manifest_extraction/`, `backend_codegen/drift.py`, and
> `wireframe/` at `0e8d08fb`. It overturned the single biggest v0.1 assumption and surfaced a quick win
> that was invisible beforehand. SDK citations are `verify-at-home`.

| v0.1 assumption | Planning discovery | Impact |
|---|---|---|
| FR-FMT-1 = "add a View-copy section to the template" (a docs edit) | **The requirements doc is a deterministic ($0, no-LLM) manifest *compiler*** (`manifest_extraction/extract.py`) that emits **6 of the 8** manifests — **not** `view_prose.yaml` (nor `display.yaml`). The view-copy *consumer* (`parse_view_prose`) exists; the *producer* (extractor) does not. | **FR-FMT-1 PROMOTED to a new Group G** — *author view copy in the reqs doc → derive `view_prose.yaml` ($0)*. A real capability, not a doc edit. |
| (not seen) | **`Empty state:` is already authored** in every `### View:` block but maps to `not_extracted(generator-gap)` (`extractors.py:241-245`) — a dead-end. The view_prose `empty` key + renderer now exist. | **New quick win (FR-VCE-2):** connect the existing-but-ignored authoring → `view_prose.yaml` `empty:`. Both ends exist; only the extractor is new. |
| (not seen) | The derivation emits **6/8** manifests; `view_prose.yaml` and `display.yaml` are both un-compiled. | New theme: **manifest-extraction parity** (FR-VCE-4 — `display.yaml` is the sibling gap). |
| Group A skip-hook needs building | The backend provider **already has** `_read_anchored()`/`_read_manifest()`/`_read_human_inputs()` — **unused** by `is_in_sync()`; `check_drift` already kind-routes + has the full signature. | **FR-DRC-3 is "wire up existing helpers,"** not new plumbing — confirms the small-thread-through verdict. |
| FR-DRC-2 = add flow kinds to `_FORMS_KINDS` | Flow kinds are in **no** kind-set AND **no** renderer map; a kind needs **both**. Flows are distinct from forms. | FR-DRC-2 reframed as a **new `_FLOWS_KINDS` family** (kind-set + checker + renderers). |
| FR-FMT-2 (lifecycle conventions) might be a parser concern | **Zero** machine consumption — the extractor ignores any non-anchored section. | **FR-FMT-2 narrowed** to a pure format-doc edit (decoupled from FR-FMT-1). |
| FR-DP-2 = extract a shared fragment primitive | The 3 mechanisms are **intentionally divergent** — AI prompts are **runtime-loaded**, not generate-time fragments. | **FR-DP-2 DROPPED** (folds into FR-DP-1 as "document the pattern + the runtime variant"). |
| FR-WCI-2 (content rollup) bundled with FR-WCI-1 as a quick win | FR-WCI-1 is quick (catalog + `Status` model exist); the **rollup** needs a new `ContentCoverageStats` + a `--json` schema bump = **medium**. | **Split FR-WCI-1 (quick) from FR-WCI-2 (medium).** |

**Resolved open questions:**
- **OQ-2 → resolved (no new plumbing).** The backend `ProviderContext` already lets the provider resolve
  every manifest via conventional `prisma/` paths (the unused `_read_anchored` helper); FR-DRC-3 is a
  small thread-through.
- **OQ-4 → resolved (drop the extraction).** FR-DP-2's shared primitive is not worth it — the mechanisms'
  time-of-binding differs fundamentally (generate-time fragments vs runtime prompt load). Document only.

---

## 1. Objectives

- **O-1** — The prime-contractor skip-hook recognizes **every manifest-derived owned file** as
  $0-deterministic when in-sync, so no such file falls through to the LLM. *(target: 0 manifest-derived
  files mis-classified; measured by a coverage test, FR-DRC-5.)*
- **O-2** — Every ecosystem surface that enumerates manifests (`ASSEMBLY_INPUTS.md`, wireframe catalog,
  capability index, kickoff template) lists `view_prose.yaml` accurately.
- **O-3a** — *(NEW — the planning unlock)* Authored view copy in the requirements doc is **deterministically
  compiled to `view_prose.yaml`** ($0, no LLM), closing the kickoff→manifest loop for the words layer and
  lighting up the already-authored `Empty state:` field. *(target: the derivation emits 8/8 manifests, not 6/8.)*
- **O-3** — The requirements/plan template + format codify the now-proven reflective-loop lifecycle and the
  Words/Structure classification, so future manifest features are authored consistently.
- **O-4** — The prose-gated additive-manifest pattern is a named, documented design principle with a single
  shared rendering primitive (de-duplicating the 3 hand-rolled copies).
- **O-5** — The fragment mechanism is reused to absorb the remaining hardcoded user-facing literals
  (low-risk quick wins).

---

## 2. Non-goals

- **Not** re-litigating the View Prose design (shipped; this is *follow-through*).
- **Not** a kickoff *manifest scaffolder* that auto-emits starter `pages.yaml`/`view_prose.yaml`/… for a
  new app — desirable but a separate, larger capability (noted as OQ-3).
- **Not** changing the drift *hash* model (whole-text per manifest stays); this only fixes which manifests
  the recognition path **threads**.
- **Not** adding new view-copy *keys* (the key-set is complete); group E only *relocates* existing literals
  and *extends* `empty`'s archetype reach.
- **No** new LLM passes — every item here is deterministic ($0) or docs.

---

## 3. Functional Requirements

### A. Drift-recognition completeness (capability-integration architectural — the critical group)

> The skip-hook (`is_deterministically_provided` → each provider's `is_in_sync`) and the in-CLI
> `--check` are **two paths to the same drift logic**, but only the CLI threads the full manifest set.
> The fix: make the skip-hook thread the same inputs the generator consumes, and add a regression lock
> so this class of gap cannot recur. Bugs A-2/A-3 were independently verified by the editors-archetype
> planning (2026-06-12); A-4 is the view_prose/display dimension this doc adds.

- **FR-DRC-1 — Explicit `KIND_TO_INPUTS` registry (LOAD-BEARING for 3+5).** The kind→manifest dependency is
  **implicit today** in the `_*_KINDS` sets + their checkers (`drift.py:47-74`); make it an **explicit**
  module-level map (kind → required manifest names) consumed by **both** the CLI `--check` and the skip-hook,
  so they can't diverge. *Verify:* a unit test asserts every owned kind has a declared input-set and both
  call sites read from it. *(This map is what makes FR-DRC-3's threading and FR-DRC-5's lock possible.)*
- **FR-DRC-2 — New `_FLOWS_KINDS` family (BUG A, verified; reframed).** `fastapi-flow` / `flow-shell`
  (`flow_generator.py:30/112`, emitted with a `forms-sha256` header) are in **no** kind-set **and no**
  renderer map — and a kind needs **both** to be drift-checkable. Add a `_FLOWS_KINDS` + `_flows_renderers()`
  (`render_flow_router`/`render_flow_shell`) + `_check_flows_drift()` (schema + views.yaml), routed in
  `check_drift` — parallel to forms, not overloaded into `_FORMS_KINDS`. *Verify:* a flows app whose
  `views.yaml` changes reports `stale`; an unchanged flows app reports `in_sync` on `generate backend --check`.
- **FR-DRC-3 — Backend skip-hook threads the kind's manifests by wiring up EXISTING helpers (BUG B,
  verified; smaller than feared).** `owned_file_in_sync()` (`drift.py:325-339`) passes only `schema_text`;
  the backend provider **already has** `_read_anchored()`/`_read_manifest()`/`_read_human_inputs()`
  (`provider.py:62-101`) but **doesn't call them**. `is_in_sync` must read the file's kind, resolve the
  manifests `KIND_TO_INPUTS` declares (via those helpers + conventional `prisma/` paths — no new plumbing,
  OQ-2 resolved), and forward them to `check_drift` — exactly as the CLI does (`cli_generate.py:280-290`).
  *Verify:* a `fastapi-web-forms`/`htmx-created` file from a non-trivial `forms:` section is recognized as
  `$0`-in-sync by the skip-hook (today it falls through to the LLM).
- **FR-DRC-4 — View provider threads display + view_prose (BUG C + consistency).**
  `CompositeViewProvider.is_in_sync` (`provider.py:25-37`) threads `view_prose_text` but **not**
  `display_text`; the CLI threads both (`cli_generate.py:466-467`). Add `display_text` resolution (~3 lines,
  mirroring view_prose) and pass it to `views_in_sync` (already accepts it). *Verify:* a view file whose only
  changed input is `display.yaml` reports not-in-sync via the skip-hook; unchanged ⇒ in-sync.
- **FR-DRC-5 — Regression lock across ALL 5 providers.** A test enumerates every owned `kind` across
  backend (`_*_KINDS` + `_renderers()` keys), view, scaffold, frontend, and polish providers and asserts the
  skip-hook re-renders each with the **same input-set** `KIND_TO_INPUTS` declares (no dropped manifest).
  *Verify:* the test fails if a future kind is added whose drift inputs the skip-hook doesn't thread.

### G. View-copy extraction — author copy in the reqs doc → derive `view_prose.yaml` ($0) *(NEW; the planning unlock)*

> The reqs doc is a deterministic ($0, no-LLM) manifest compiler (`manifest_extraction/`) that emits 6 of
> the 8 cascade manifests; `view_prose.yaml` is one of the two it doesn't. The *consumer*
> (`parse_view_prose`) is shipped — only the *producer* (extractor) is missing. This group closes the loop
> and lights up an already-authored, currently-dead field.

- **FR-VCE-1 — `extract_view_prose()` in `manifest_extraction`.** Add an extractor that parses per-view
  copy keys from each `### View:` block (the block already uses the `- Key: value` grammar), wired into the
  candidate set (`extract.py:145-158`) and the round-trip table (`extract.py:162-175`) calling the
  **existing** `parse_view_prose(text, known_views=…)` so a bad copy block fails **at ingestion** (loud,
  FR-WPI-4), not at `generate views`. *Verify:* a reqs doc with view copy yields a valid `view_prose.yaml`
  in the emitted manifest set; an archetype-invalid key fails ingestion loudly.
- **FR-VCE-2 — Close the `Empty state:` dead-end (the quick win).** `Empty state:` is **already authored**
  in every `### View:` block but maps to `not_extracted(generator-gap)` (`extractors.py:241-245`). Route it
  to `view_prose.yaml` `empty:` for model-scoped detail-compose views — existing authoring → existing
  renderer, only the extractor is new. *Verify:* a view declaring `Empty state:` produces an `empty:` entry;
  the generated page shows that copy.
- **FR-VCE-3 — Per-archetype validity is end-to-end (no new validator).** The extractor emits the keys; the
  **shipped renderer already rejects** archetype-invalid combinations (`renderers.py:1862-1881`:
  `empty`→detail-compose-model, `success`/`error`/`controls`→import-flow). *Verify:* `empty` authored on a
  computed-panel fails the round-trip at ingestion (reusing the renderer's loud-fail).
- **FR-VCE-4 — Manifest-extraction parity (`display.yaml` sibling).** The same gap exists for the structure
  layer: the derivation doesn't emit `display.yaml` either. Add a `display.yaml` extractor so the kickoff
  derivation reaches **8/8** manifest parity with the $0 cascade. *Verify:* `generate schema
  --with-manifests` emits `view_prose.yaml` and `display.yaml` alongside the existing six. *(Separable
  increment; lower urgency than VCE-1/2.)*

### B. Kickoff inputs & assembly-inputs consistency

- **FR-KIN-1 — Correct the `ASSEMBLY_INPUTS.md` view_prose entry.** The strtd8 inventory still describes
  the *overruled* design ("→ `views.yaml` `prose:` … parked until strict-parse supports the `prose:` key").
  Replace it with the shipped reality: a **standalone `prisma/view_prose.yaml`** consumed by
  `generate views --view-prose`, hash-exempt (rendered to untracked fragments), full key-set
  title/intro/empty/success/error/controls. *Verify:* the entry's "Drives" column reads
  `generate views --view-prose` and the lifecycle column reads "outside the drift hash".
- **FR-KIN-2 — Kickoff inputs taxonomy classifies view_prose explicitly.** Confirm/keep the
  `KICKOFF_INPUTS_EXPLAINED.md` taxonomy places `view_prose.yaml` on the **content-prose / hash-exempt /
  author→approve** side (not the structural/hashed side), beside `app/pages/*.md`. *Verify:* the taxonomy's
  Words/Structure split names `view_prose.yaml` under Words.
- **FR-KIN-3 — The `ASSEMBLY_INPUTS_TEMPLATE.md` carries a view_prose row.** The reusable inventory
  template (SDK kickoff) gains a placeholder row for `prisma/view_prose.yaml` so every new project's
  inventory includes it. *Verify:* the template lists view_prose with `<status>` placeholder.

### C. Requirements format & template updates

- **FR-FMT-1 — The template's "View copy" keys (the *authoring surface* for Group G).** Add the per-view
  copy keys to the `### View:` block in `REQUIREMENTS_TEMPLATE.md` (title/intro/empty/success/error/controls,
  parallel to the existing `Empty state:` line) + a `[consumed by: extraction → view_prose.yaml]` annotation
  in `REQUIREMENTS_AND_PLAN_FORMAT.md`. **Pairs with FR-VCE-1** (the extractor that consumes them) — together
  they make view copy authorable-then-derivable. *Verify:* the format doc lists the keys' exact grammar under
  the View block; FR-VCE-1's extractor reads them.
- **FR-FMT-2 — Codify the reflective-loop lifecycle conventions (PURE doc — no parser, planning-confirmed).**
  The lifecycle is **human convention only** (the extractor ignores any non-anchored section), so this is a
  format-doc + scaffold edit with zero parser risk. Make first-class in `REQUIREMENTS_AND_PLAN_FORMAT.md`:
  a `§0 Planning Insights` table (v(n-1)→v(n) discoveries), the `Appendix A/B/C` CRP review-log scaffold,
  the "What changed in vX" callout convention, the version/date *lineage* header, and an
  **"Implementation Reflections"** convention (Phase-6 findings fed back, as v0.7→v0.9 did). *Verify:* the
  format doc names each convention with an example; the template ships the empty scaffolds.
- **FR-FMT-3 — Add the Words/Structure classification rule.** The format gains a one-paragraph rule: any
  *new file-shaped input* is classified **hashed-structure** (a `views.yaml` section / standalone hashed
  manifest) **or** **hash-exempt-prose** (a standalone file rendered to an untracked fragment), and routed
  accordingly. *Verify:* the rule cites the shipped split (display.yaml=structure, view_prose.yaml=words).
- **FR-FMT-4 — Add the `$0`-codegen acceptance-criteria checklist.** Capture the recurring ACs proven by
  View Prose as a reusable checklist for any deterministic-manifest feature: **byte-identical-when-absent**,
  **fail-closed on a malformed manifest**, **drift-stability** (editing hash-exempt content never trips
  `--check`), **strict loud-fail parse**, **prose-gated opt-in** (no downstream drift). *Verify:* the
  checklist appears in the format/authoring guide and is referenced from the View-copy section.

### D. Wireframe & capability-index integration

- **FR-WCI-1 — Wireframe reports view-copy coverage (QUICK — catalog + Status model exist).** Add
  `"view_prose": "prisma/view_prose.yaml"` to `wireframe/inputs.py:30-38` CONVENTION_PATHS; a
  `_view_prose_state()` parallel to `_yaml_state()`; extend `_views_section()` (`plan.py:586-636`) to emit
  per-view chrome status using the existing `Status` model (`plan.py:45-50`). *Verify:* `startd8 wireframe`
  lists each view's copy status; a view with no `view_prose.yaml` entry reads `not_defined`/raw.
- **FR-WCI-2 — A unified "content/words completeness" rollup (MEDIUM — split from WCI-1).** Planning found
  the wireframe has per-surface status but **no aggregation**; a rollup needs a new `ContentCoverageStats`
  (pages + view copy + AI prompts) in `build_wireframe_plan()` + a `--json` `content_completeness` block
  (schema-version bump). *Verify:* the `--json` output carries the rollup; a separate, lower-urgency
  increment from WCI-1.
- **FR-WCI-3 — Capability-index entry for composite views + view copy.** Register
  `startd8.codegen.composite_views` (the view_codegen generator) and `startd8.codegen.view_prose` (the
  view-chrome capability) in `docs/capability-index/startd8.sdk.capabilities.yaml`, with evidence pointers
  and the multi-audience description. *Verify:* `/capability-index` validation passes with the two new
  entries.

### E. Functional quick wins (unblocked by the shipped fragment mechanism)

- **FR-QW-1 — Extend `empty` to the other no-rows surfaces.** The untracked empty-fragment mechanism now
  exists; extend `empty` from model-compose to the `detail-compose` index "pick-an-item" page
  (`renderers.py:967`) and the `rendered-content` list empty (`:1026`), with the per-archetype guard. *Verify:*
  `empty` on those archetypes renders via a fragment and stays byte-identical when absent; on an archetype
  with no no-rows surface it still loud-fails.
- **FR-QW-2 — Route remaining hardcoded user-facing literals through prose (opt-in).** The
  `computed-panel` "All signals met." complete-state (`:1074`), the rendered-content "Nothing to read yet."
  (`:1021`), and the index prompt are authored copy baked in the renderers. Make each prose-overridable via
  an existing or minimal key, **defaulting to today's literal** (zero behavior change absent prose). *Verify:*
  each literal is overridable; absent prose ⇒ byte-identical.
- **FR-QW-3 — Finish the control follow-ups' tail.** Surface the deferred bits now that the mechanism is
  proven: a validate-success result line (today validate stays JSON) and per-control help on the export
  links — both prose-gated. *Verify:* authoring them renders; absent ⇒ byte-identical. *(Lower priority;
  may stay deferred.)*

### F. Design-principle elevation (architectural generalization)

- **FR-DP-1 — Name & document the prose-gated additive-manifest principle.** Add a cross-cutting principle
  doc (`docs/design-princples/`, beside MOTTAINAI/KAIZEN/WARM_UP/HAYAI) capturing the proven rule:
  *hash-exempt authored content lives in a standalone file rendered to an untracked (header-less) fragment;
  the owned template gains the include only when the content is present → byte-identical-when-absent → zero
  downstream drift.* Cover the **generate-time fragment** instances (pages + view-prose), and note the
  ai-layer prompt as a **related runtime-binding variant** (read at request time, not a generate-time
  fragment — planning, D8). *Verify:* the principle doc exists and is linked from the Words/Structure rule
  (FR-FMT-3).
- **~~FR-DP-2 — Extract a shared untracked-fragment primitive.~~ DROPPED (planning, D8).** The three
  mechanisms are **intentionally divergent** — pages/view-prose are generate-time fragments; the ai-layer
  prompt is **runtime-loaded** (`ai_layer.py:695-700`), not a fragment at all. Time-of-binding, format
  (markdown vs escaped vs raw), and discovery all differ, so a shared primitive isn't worth it (and is
  partly impossible). The pattern is **documented** by FR-DP-1 instead of extracted.

---

## 4. Open Questions (updated after planning)

- **OQ-1 — Carve group A out?** Group A (drift-recognition) is urgent, SDK-internal, and pre-dates
  view_prose. Recommend its own requirements doc + PR; this doc keeps the rest. *(Still open — decide at
  CRP/impl time.)*
- **OQ-2 — ✅ RESOLVED (planning).** No new plumbing: the backend `ProviderContext` already lets the
  provider resolve every manifest via conventional `prisma/` paths (the unused `_read_anchored` helper).
  FR-DRC-3 is a small thread-through.
- **OQ-3 — Kickoff manifest scaffolder.** Should the kickoff *emit* starter manifests for a new app? Note:
  Group G (FR-VCE-*) is the **derivation** path (reqs → manifests); a blank-scaffold path is a *different*,
  bigger capability. Deferred unless prioritized.
- **OQ-4 — ✅ RESOLVED (planning, D8).** FR-DP-2 dropped — the three mechanisms diverge (ai-layer is
  runtime-bound); document via FR-DP-1, don't extract.
- **OQ-5 — Wireframe rollup scope (FR-WCI-2).** Three-surface rollup (pages + view copy + AI prompts) the
  right denominator, or also form blurbs / entity titles? *(Keep v1 to the three; expand later.)*
- **OQ-6 (NEW) — Group G ingestion ordering.** FR-VCE-1 must run `parse_view_prose(known_views=…)` in the
  round-trip — which needs the **views** already extracted (to know the view names). Confirm the
  `extract.py` candidate ordering makes views available before view_prose. *(Verify-at-home; likely just
  ordering within `extract.py:145-158`.)*

---

## 5. Priority / sequencing (updated after planning)

1. **A (drift-recognition completeness)** — highest value; fixes silent $0→LLM fallthrough + 3 verified
   bugs; small thread-through (helpers already exist). Its own PR (OQ-1). *FR-DRC-1 first (unblocks 3+5).*
2. **G (view-copy extraction)** — highest *value* unlock; **FR-VCE-2 (close `Empty state:`) is the cheapest
   first slice** and proves the path; pairs with FR-FMT-1.
3. **D (FR-WCI-1 wireframe + FR-WCI-3 cap index)** — quick wins.
4. **C / B / F-doc** — cheap docs: FR-FMT-2/3/4 (no parser), FR-KIN-*, FR-DP-1.
5. **FR-WCI-2 (rollup)** + **FR-VCE-4 (display extraction parity)** — medium follow-ups.
6. **E (quick wins)** — opportunistic; lowest urgency.

---

*v0.2 — Post-planning self-reflective update (reflective loop Phase 4). Plan
`VIEW_PROSE_FOLLOWTHROUGH_PLAN_v0.1.md` (grounded at `0e8d08fb`) drove: **FR-FMT-1 promoted to a new Group
G** (the reqs doc is a deterministic $0 manifest compiler that doesn't yet emit `view_prose.yaml`); a **new
quick win FR-VCE-2** (the already-authored `Empty state:` dead-end the view_prose machinery can now light
up); a **manifest-extraction-parity** theme (FR-VCE-4 / display.yaml — the derivation emits 6/8). Group A
confirmed a small thread-through (helpers exist, unused); FR-DRC-2 reframed as `_FLOWS_KINDS`; FR-DRC-5
widened to all 5 providers. FR-FMT-2 narrowed to pure doc; **FR-DP-2 dropped**; **FR-WCI split** (1 quick, 2
medium). OQ-2/OQ-4 resolved; OQ-6 added.*
*v0.1 — Initial draft (Phase 1), grounded in SDK `main` @ `0e8d08fb` + strtd8 kickoff/assembly docs.*

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
