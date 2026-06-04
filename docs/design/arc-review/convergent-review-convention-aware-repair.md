# Convergent Review Prompt

**Generated:** 2026-06-04 03:34:08 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/repair-pipeline/CONVENTION_AWARE_REPAIR_PLAN.md` | 109 lines · 1010 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md` | 318 lines · 3485 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/convention-aware-repair-focus.md` | 35 lines · 323 words |

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

# CRP Focus — Convention-Aware Repair (v0.2 requirements + plan)

Pre-implementation architectural review of a design that changes **shared contracts** across the
codegen pipeline. Weight findings toward where a wrong abstraction is expensive to undo later.

## Where we need input most

1. **FR-CAR-0 abstraction (critical path).** The "PythonConventionAuthority derived from the generators"
   is the foundation everything else consumes. Is deriving convention rules *from* the generator renderers
   the right source of truth — vs. extending `project_knowledge`'s producer, vs. a generator-adjacent
   manifest? What breaks if the authority and the generators drift? Is "derive from generators" even
   mechanically clean (the renderers encode idioms in Python string templates, not a declarative form)?

2. **Escalation-contract change.** FR-CAR-6 adds `RepairOutcome.unrepaired_diagnostics` and a residual
   payload on `EscalationHandoff` (Keiyaku K-6). Does this compose with the existing iterative-repair
   "complete true residual" (`REPAIR_RETRY_ITERATIVE`) and the K-6 contract, or duplicate/conflict with it?
   Is there one residual concept or two?

3. **Verdict-term change.** FR-CAR-7 adds a convention factor / hard-gate to `compute_disk_quality_score`.
   Risks: double-counting against `semantic_issues`; destabilizing existing scores/thresholds; interaction
   with the corpus's req-score (are there now two semantic-compliance numbers that can disagree?). Hard-gate
   (any convention error → 0.0) vs. weighted term — which, and why?

4. **Polyglot retrofit (FR-CAR-8).** Bringing the existing hand-coded C#/Go/Java convention steps under the
   FR-CAR-0 authority+parity discipline is a refactor of *working* code. Is the value worth the regression
   risk? Should it be deferred behind the Python proof, or is the unified model load-bearing from day one?

5. **Safe-fix vs escalate boundary (FR-CAR-4).** False-positive risk on legitimately dual-pattern code
   (e.g. `app/ai/extract.py` supports both `session.query` and `select`). Is "authority-scoped, AST-local,
   single-symbol, revert-on-break" a sufficient guard, or does deterministic convention rewriting need a
   tighter contract before it's safe to enable?

6. **Sequencing / advisory ramp.** Phase A is advisory-only; B flips behavior (escalation + verdict). Is
   the advisory→gating ramp staged safely (false-positive measurement before any FAIL)? Is FR-CAR-0 truly
   the only critical-path blocker, or are the model-contract changes (FR-CAR-6) independently sequenceable?

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/repair-pipeline/CONVENTION_AWARE_REPAIR_PLAN.md`  ·  **Size:** 109 lines · 1010 words

```markdown
# Convention-Aware Repair — Implementation Plan

**Version:** 0.2 · **Pairs with:** `CONVENTION_AWARE_REPAIR_REQUIREMENTS.md` (v0.2)
**Date:** 2026-06-03

> Sequenced around the planning-pass discoveries: most FRs **extend established patterns** (the
> `convention` category already exists for C#; `content_contract` already detects wrong imports), but
> everything is **gated on FR-CAR-0** — the Python convention source-of-truth, which does not exist yet.

## Seam map (from the Phase-2 exploration)

| Concern | Existing seam (file:line) | Change |
|---|---|---|
| Convention rule source | `contractors/project_knowledge/{models,producer,negatives}.py` (TS/Prisma-only) | extend to Python + add framework/ORM authority (FR-CAR-0) |
| Diagnostic taxonomy | `repair/models.py` (`semantic`/`content_contract` subclasses) | add `ConventionDiagnostic` (FR-CAR-1) |
| Routing | `repair/routing.py:150` (`convention` route for C#) | add Python `convention` routes (FR-CAR-1) |
| Existing partial detection | `WrongImportPathDiagnostic`/`MisnamedFieldDiagnostic` (`models.py:128,146`) | reuse for `module_source` (FR-CAR-3) |
| Repair context | `RepairContext` carries `project_root`/`manifest_registry` (`models.py:234`) | add `convention_authority` handle (FR-CAR-2) |
| Residual escalation | `RepairOutcome` (`models.py:278`) has no residual; `_run_post_generation_repair` returns int | add `unrepaired_diagnostics`; rewire to escalate (FR-CAR-6) |
| In-run handoff | `EscalationHandoff` (`micro_prime/models.py:139`) prose-only | add residual payload (FR-CAR-6) |
| Verdict | `compute_disk_quality_score` (`forward_manifest_validator.py:553`) | add convention term / hard-gate (FR-CAR-7) |
| micro-prime injection | `MicroPrimeContext` (`context.py:11`) → `process_file_with_context` (`engine.py:2557`) | add field + thread (FR-CAR-5) |

## Phases

### Phase A — Authority + detection (advisory; no behavior change) — FR-CAR-0/1/2/3
1. **`PythonConventionAuthority`** (FR-CAR-0): a deterministic producer derived from `backend_codegen`
   (`CANONICAL_LAYOUT` → module-source: tables=`app.tables`, schemas=`app.models`; renderer idioms →
   framework=FastAPI, orm=SQLModel, template=`Jinja2Templates`) + a generator-derived `Negative` set
   (Flask→FastAPI, `session.query`→`select`, table-from-`app.models`→`app.tables`). Live next to / inside
   `project_knowledge` so one artifact serves all consumers; extend the producer to read `.py`.
2. **`ConventionDiagnostic`** subclass + register the Python `convention` routes (mirror the C# route).
3. **Detectors**: reuse `content_contract` for `module_source`; new AST/regex detectors for `framework`,
   `orm_idiom`, `template_idiom`, sourced from the authority (not hardcoded).
4. **Parity test** (FR-CAR-2/8): generate an app (the pilot schema), corrupt each convention, assert the
   detector fires. Seed fixtures from RUN-028's `…/generated/app/jobs.py`.
   *Exit A:* detection emits `ConventionDiagnostic`s; nothing fails yet (advisory).

### Phase B — Escalate-don't-silence + verdict (the RUN-028 fix) — FR-CAR-4/6/7
5. **Safe fixers** (FR-CAR-4): deterministic, revert-on-break — `session.query(X).get(id)`→`session.get(X,id)`;
   wrong-module import→canonical (reuse `content_contract` fixers). Wholesale framework wrong → no fix.
6. **Residual plumbing** (FR-CAR-6): add `RepairOutcome.unrepaired_diagnostics`; populate it in the
   orchestrator; rewire `_run_post_generation_repair` to return/raise on residual convention diagnostics
   instead of dropping. Add residual payload to `EscalationHandoff` for the in-run path.
7. **Verdict term** (FR-CAR-7): add a dedicated convention factor (or hard-gate: any error-severity
   convention violation → 0.0) to `compute_disk_quality_score`; register `convention` distinct from
   `semantic_issues`. **Symptom-fix guard test:** a file with both an F811 and a Flask import must FAIL even
   after the F811 is auto-fixed.
   *Exit B:* RUN-028 replay → the wrong-framework file FAILS loudly (not lint-clean PASS), with the residual
   escalated.

### Phase C — Reach the cheapest tier — FR-CAR-5
8. Thread the authority into micro-prime: add a `MicroPrimeContext` field, populate from `gen_context` in
   `from_prime` (prime_contractor holds `self._project_knowledge`), pass through
   `process_file_with_context` → `process_file` → prompt builders. Measure adherence lift on the micro-prime
   tier against the RUN-028 corpus (structural scoring, per the CKG methodology gate).

### Phase D — Lock-step + learning — FR-CAR-8/9/10
9. **Parity-in-lock-step** (FR-CAR-8): a meta-test asserting every owned-artifact kind in `CANONICAL_LAYOUT`
   (+ pages kinds) has a convention rule + parity fixture; a new generator without coverage fails CI.
10. **Telemetry → Kaizen** (FR-CAR-9): OTel counters (category/rule/tier/outcome) + a
    `requirement_convention_gap` CAUSE_TO_SUGGESTION; feed recurring per-tier violations to the classifier
    signal (postmortem A1 / D3). Keep everything deterministic/no-LLM (FR-CAR-10).

## Verification
- Unit: detector parity (generate→corrupt→detect) per convention; safe-fixer round-trips; residual surfaced;
  verdict FAILs a lint-clean wrong file; symptom-fix guard.
- Integration: RUN-028 `jobs.py` replay → detected + escalated + FAILED (today: silent PASS at micro-prime).
- **Corpus fixtures:** seed detectors + parity tests from the Controlled Corpus `false_pass_risk` set
  (`docs/design/controlled-corpus/`), esp. the Flask-RAG `shoppingassistantservice.py` (stability 1.0 /
  req 0.5) — the convention detector must flag it and the verdict term must score it failing, demonstrating
  the two-axis (structural × semantic) gate.
- Cross-tier: micro-prime adherence lift on the corpus after Phase C.
- **Regression guard against the symptom-fix trap:** assert that applying the F811 dedup (`886dccbd`) to a
  Flask file does NOT raise its disk-quality score (the convention term holds it failing).

## Risks / open
- FR-CAR-0 is the critical path; if the authority can't be cleanly derived from the generators, fall back to
  a small generator-adjacent convention manifest (still parity-tested) — but avoid a hand-maintained list.
- False positives on `module_source`/`orm_idiom` in legitimately dual-pattern code (e.g. `app/ai/extract.py`
  supports both `session.query` and `select`) — detectors must be authority-scoped, not blanket grep.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md`  ·  **Size:** 318 lines · 3485 words

```markdown
# Convention-Aware Repair — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-03
**Status:** Draft for review — pairs with `CONVENTION_AWARE_REPAIR_PLAN.md`
**Aligns with:** `REPAIR_RETRY_ITERATIVE_REQUIREMENTS.md` (the "complete true residual, don't mask" framing),
`POST_GENERATION_REPAIR_PIPELINE_REQUIREMENTS.md`, `MANIFEST_DRIVEN_NAME_REPAIR_*`
**Motivating evidence:** `strtd8/docs/P2_RUN_028_POSTMORTEM.md` (micro-prime emitted Flask-not-FastAPI,
`session.query`, table-from-`app.models`; the build gate caught only the F811 symptom).

---

## 0. Planning Insights (Self-Reflective Update: v0.1 → v0.2)

> The planning pass (3 parallel code explorations) tested v0.1's assumptions against the actual
> `project_knowledge`, repair, escalation, and verdict code. It revealed **6 corrections** — a
> >30% revision, which means v0.1 was premature in exactly the way the loop is meant to catch.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| `project_knowledge` is the source of truth for framework/ORM/module-source house style (FR-CAR-2) | `ProjectKnowledge` (`contractors/project_knowledge/models.py:76`) encodes module-source (`UpstreamInterface`), `Negative` (invented→correct), field-sets, enums, omissions — **but the producer reads only `.ts/.tsx/.js` + `schema.prisma` and `@/`-aliases (TS/Prisma-ONLY), and encodes NO framework/ORM idiom at all.** For a Python project it yields nothing useful. | **NEW FR-CAR-0 (foundational) + FR-CAR-2 reframed:** the Python convention source-of-truth **does not exist yet** and must be built. The deterministic generators (`backend_codegen` renderers) are the de-facto authority; the rule set must be **derived from them** (and the producer extended to Python). |
| Adding a `convention` Diagnostic category is greenfield (FR-CAR-1) | The **`convention` category ALREADY EXISTS** in `repair/routing.py:150` — for C# (`csharp_convention_error` → `csharp_convention_fix`). Convention-repair is an **established pattern**; there's no `ConventionDiagnostic` dataclass yet (C# routes on the category string + a language step). | **FR-CAR-1 narrowed:** *extend* the existing convention category to Python (a `python_convention_fix` step + a `ConventionDiagnostic` subclass), not invent it. De-risks significantly. |
| Detection is greenfield (FR-CAR-3) | `content_contract` detectors already exist: `WrongImportPathDiagnostic` (invented module specifier) + `MisnamedFieldDiagnostic` (invented Prisma field, via `scan_prisma_usage`) (`repair/models.py:128,146`). Module-source/import detection **partly exists**. | **FR-CAR-3 narrowed:** reuse/extend `content_contract` for `module_source`; build only the `framework` / `orm_idiom` / `template_idiom` detectors. |
| Repair can escalate unrepaired diagnostics (FR-CAR-6) | `RepairOutcome` (`repair/models.py:278`) has **no residual field**; `EscalationHandoff` (`micro_prime/models.py:139`) carries prose `failure_message` + repair-step details, **no structured diagnostic payload**; `_run_post_generation_repair` returns a **count** and drops the rest. | **FR-CAR-6 made concrete:** two model changes required — add `unrepaired_diagnostics` to `RepairOutcome`, add a residual payload to `EscalationHandoff` (or a sibling channel) — plus rewiring the post-gen repair to act on them. |
| Convention residue fails the verdict by feeding `semantic_issues` (FR-CAR-7) | `compute_disk_quality_score` (`forward_manifest_validator.py:553`) weights `semantic_penalty` at only **0.2**, and hard-zero applies **only** when `ast_valid=False`. A lint-clean, AST-valid wrong-framework file would still score **~0.8** even with convention errors in `semantic_issues`. | **FR-CAR-7 reframed:** failing a lint-clean wrong file needs a **dedicated convention term / hard-gate** in the score formula — appending to `semantic_issues` is insufficient. |
| Injecting adherence into micro-prime is a prompt tweak (FR-CAR-5) | Clean seam exists (`MicroPrimeContext` → `process_file_with_context` → `process_file`, `micro_prime/context.py:11`, `engine.py:2557`) but **nothing project-knowledge-shaped is threaded**, and `gen_context` doesn't carry `project_knowledge` into `from_prime`. It is also **blocked on FR-CAR-0** (no Python conventions exist to inject). | **FR-CAR-5 sequenced after FR-CAR-0:** add a `MicroPrimeContext` field + thread from `gen_context` (where prime_contractor holds `self._project_knowledge`). Only meaningful once Python conventions exist. |

**Resolved open questions**
- **OQ-1 (source of truth) → none exists for Python; build it (FR-CAR-0).** `project_knowledge` is TS/Prisma-only and framework/ORM-blind. The generators are the de-facto authority → derive the convention rule set from them and extend the producer to Python.
- **OQ-2 (safe-fix vs escalate) → reuse the C# convention-fix precedent.** Deterministic, AST-local, revert-on-break. `module_source`/import rewrites are safe (reuse `content_contract` fixers); wholesale `framework`/`orm` rewrites escalate.
- **OQ-3 (in-run vs post-run) → both, one rule set.** In-run via an extended `EscalationHandoff` (micro-prime element path); post-run via the iterative residual + `RepairOutcome.unrepaired_diagnostics`. Both consume the FR-CAR-0 source.
- **OQ-4 (relationship to existing categories) → extend, don't double-count.** `module_source` reuses `content_contract`; `convention` = framework/ORM/template idiom (new). Must register as a **distinct** category in the verdict, not conflate with `semantic_issues` (FR-CAR-7).
- **OQ-5 (cross-tier) → detect on all tiers; inject preferentially on micro-prime** (weakest adherence, largest validated lift).
- **OQ-6 (symptom-fix linkage) → file-scoped.** `RepairOutcome` is file-granular; flag a residual `convention` diagnostic in the same file as a mechanical fix.
- **OQ-7 (bootstrap corpus) → yes.** RUN-028's rejected `jobs.py` lives under the run's `…/generated/app/jobs.py`; use it as the seed fixture for FR-CAR-3 detectors and FR-CAR-2 parity tests.

### Cross-project evidence (online-boutique-demo) — the pattern is already polyglot

A second exploration (`online-boutique-demo`, the SDK's Go/Java/C#/Node/Python microservices benchmark)
shows **convention-aware repair is NOT Python-greenfield — it already exists per-language**, born from those
runs:
- **C#:** `csharp_convention_fix` / `csharp_namespace_fix` / `csharp_nullable_fix` / `csharp_access_modifier`,
  with a dedicated `("convention", "csharp_convention_error", …)` route (`routing.py:150`).
- **Go:** `go_dot_import_cleanup` / `go_contamination_strip` / `go_unchecked_error`; RUN-120 surfaced
  **package-declaration consistency** as a convention failure (REQ-KZ-GO-606).
- **Java:** `java_missing_override` / `java_raw_type_fix` / `java_import_sort` / `java_duplicate_method`.

**Two consequences for this spec:**
1. **FR-CAR-1 is de-risked further** — `csharp_convention_fix` is a *complete working template* for a
   `python_convention_fix` step; the Python gap is that `backend_codegen` (the newest generator) has **no**
   convention step, only AST/semantic checks.
2. **The existing per-language steps are hand-coded → exactly the drift risk FR-CAR-0/2 exist to kill.**
   `csharp_convention_fix` hardcodes C# rules with no parity tie to a C# generator. So FR-CAR-0's
   **authority + parity** discipline should **retro-cover the existing C#/Go/Java steps too** (FR-CAR-8 is
   not Python-only). Corpus expands: RUN-028 (Python) **+** RUN-120 (Go) **+** the C# convention runs.

### Cross-project evidence (controlled-corpus) — the convention-false-PASS class is already labeled

The Controlled Corpus (`docs/design/controlled-corpus/`, mined from the 37-run online-boutique trove,
5 languages, Claude+Gemini) supplies three things this spec needs:
1. **A two-axis determinism model: structural stability × semantic compliance (req-score)** — *exactly* the
   distinction at the heart of this spec. A convention violation is a failure on the **semantic axis** while
   the **structural axis is clean** (builds/lints fine).
2. **It already labels the class** as `false_pass_risk` (stable build **but** req-score <0.7 → "must stay
   LLM + SCR"). The headline example is **`shoppingassistantservice.py` — the *Flask* RAG, stability 1.0 /
   req 0.5**: a real, cross-run-stable, **wrong-framework** false-PASS. That is independent corroboration of
   the RUN-028 class **and a ready-made fixture** (OQ-7 widens: RUN-028 jobs.py + the corpus `false_pass_risk`
   set, not just one file).
3. **The symptom-fix risk, located precisely (not a corpus defect).** The inventory's *"run-028 class …
   now fixed via the F811 repair 886dccbd"* is **correct in its context** — it is in the *corpus-widening*
   caveat and means the build-FAIL **blocker to accumulating green runs** clears, so the corpus can widen.
   The corpus's **req-score axis already handles the convention defect right** (the Flask RAG stays
   `false_pass_risk` at req 0.5, independent of the F811 fix — the corpus is **not** fooled). The symptom-fix
   trap this spec targets lives **one layer over**, at the **disk-quality verdict** (`compute_disk_quality_score`:
   `ast_valid` + a 0.2-capped semantic penalty), where a now-lint-clean Flask file would wrongly score ~0.8.
   So the corpus is the **proof the two-axis gate works**; FR-CAR-6/7's job is to bring the *verdict* up to
   that standard, not to correct the corpus.

**Implications for the spec:**
- **FR-CAR-7 must align with the two-axis model the corpus already uses** — "structurally clean" must not
  imply PASS at the verdict layer; the convention (semantic-axis) term is the missing factor *there*.
- **FR-CAR-0 consumes/feeds the corpus, but is still net-new for framework/ORM.** `corpus/view.as_project_knowledge()`
  is currently a **boundary shim** (CKG authorities empty); the corpus is the determinism **classifier** +
  fixture source, not yet the framework/ORM authority. The corpus tells you *which* target files are
  `deterministic_candidate` vs `false_pass_risk`; the convention **rules** (FastAPI-not-Flask) are still
  generator-derived (FR-CAR-0). The two compose: corpus = where to look; authority = what's correct.

---

## 1. Problem Statement

We have steadily **expanded the surface we can deterministically generate** — the all-Python backend
(`backend_codegen/`: Pydantic + SQLModel + FastAPI + HTMX), content pages (`pages_generator.py`), and
the CKG knowledge-provider's adherence injection (`contractors/project_knowledge/adherence.py`:
field-set authority + module-path negatives, validated to lift cheap-tier adherence ~0.05–0.40 → ~1.0).
**The repair pipeline has not kept pace.** Repair is purely *mechanical* (syntax / AST / imports / lint /
indentation / duplicates); it does not know the house style those generators encode. RUN-028 made the
gap concrete: micro-prime produced architecturally-wrong-but-valid-Python code that passed **every**
repair gate, and only a top-level F811 tripped the external build gate.

### Gap table — deterministic-generation capability vs. repair coverage

| House-style capability (we generate it) | Encoded in | Present in repair? | Gap |
|---|---|---|---|
| FastAPI routing (`APIRouter`/`Depends`/`HTMLResponse`) | `crud_generator`, `htmx_generator` | ❌ | Flask code is valid Python → passes syntax/AST/lint; never flagged |
| SQLModel access (`session.exec(select(...))`, `session.get`) | `crud_generator` | ❌ | `session.query(X).get(id)` not detected/fixed |
| Table source = `app.tables`; Pydantic `*Schema` = `app.models` | `crud`/`ai_layer` | ⚠️ partial | post-028 `duplicate_removal` drops a dup *import* (886dccbd) but there is **no positive** "import the table from `app.tables`" |
| Jinja2Templates / `TemplateResponse` (the `value_map.py` pattern) | `htmx_generator`, `pages_generator` | ❌ | `render_template(...)` / Flask response tuples not flagged |
| Module-path **authority + negatives**, field-set authority | `project_knowledge/adherence.py` | ⚠️ lead/drafter only | `micro_prime/` has **zero** `project_knowledge` refs → the cheapest tier never receives it |
| **Escalate on unrepairable** | — | ❌ | `prime_adapter._run_post_generation_repair` returns a *count* and continues; diagnostics it can't fix are **dropped**, not escalated |

### Three failure modes (RUN-028)
1. **Convention-blind.** Wrong framework / ORM / module-source is valid Python → every mechanical gate passes.
2. **Adherence bypass.** The validated injection reaches only the lead/drafter path; micro-prime generates
   (and self-repairs) with no house-style knowledge.
3. **Silence-not-escalate, and the symptom-fix trap.** Repair drops what it can't fix; worse, the new
   cross-kind F811 fix (886dccbd) can make a wrong-framework file **lint-clean**, converting a loud FAIL
   into a quiet wrong-but-passing output.

---

## 2. Goal

Make repair **convention-aware**, deriving the house style from the **same source the generators encode**
(no hand-maintained parallel catalog that drifts — the CRP validator-parity lesson), so it can: detect the
convention class, **deterministically fix what is unambiguously safe**, and **route the rest to the true
residual + escalation — never silence it**. Bring each *expanding* deterministic-generation capability into
repair **in lock-step**, so the two never diverge again.

---

## 3. Functional Requirements

### FR-CAR-0 — Python convention source-of-truth (FOUNDATIONAL; NEW in v0.2)
There is **no existing artifact** that encodes the Python house style (framework, ORM idiom,
module-source authority) in a consumable form — `project_knowledge` is TS/Prisma-only and framework/ORM-blind.
Build it: a deterministic **`PythonConventionAuthority`** derived from the **generators themselves** (the
`backend_codegen` renderers are the de-facto truth — e.g. `CANONICAL_LAYOUT` knows tables live in
`app.tables`, the renderers emit FastAPI/SQLModel/`Jinja2Templates`), plus **generator-derived negatives**
(the Python analogue of the seeded TS `Negative`s: Flask→FastAPI, `session.query`→`session.exec(select())`,
table-from-`app.models`→`app.tables`). Extend the `project_knowledge` producer to read `.py` so the same
artifact serves all consumers. **Everything below consumes FR-CAR-0; it is the prerequisite.**

### FR-CAR-1 — `convention` diagnostic category
**v0.2 (narrowed): the `convention` category already exists** (`repair/routing.py:150`, used by C#). Add a
`ConventionDiagnostic` subclass to the taxonomy (`repair/models.py`, alongside `semantic` /
`contract_violation` / `content_contract`) with sub-kinds `framework`, `orm_idiom`, `module_source`,
`template_idiom`, `response_idiom`, carrying the offending span + canonical expectation + `safe_fixable: bool`;
and add **Python routes** to the routing table (the C# convention route is the working precedent to mirror).

### FR-CAR-2 — Single source of convention truth (parity-enforced)
Convention rules MUST derive from the **FR-CAR-0 `PythonConventionAuthority`** (itself derived from the
generators), **not** a hand-maintained parallel list. A **parity test** is required: a file produced by a
generator, then corrupted to violate a convention, MUST be detected by the repair detector. (Mirrors the
content-pages CRP R1-F4/S4 "validator ≡ generator" guard.)
**v0.2 note:** the existing seeded TS `Negative`s (`@/lib/prisma`→`@/lib/db`) are the working *pattern* to
follow, but they are TS-specific — the Python negatives are a new, generator-derived set (FR-CAR-0), not a
reuse of the TS ones.

### FR-CAR-3 — Detect the RUN-028 convention class
The detector MUST flag, at minimum: wrong **framework** (Flask import / `@app.route` / `render_template`
in a FastAPI project), wrong **ORM idiom** (`session.query(...)`, `.query(...).get(...)`), wrong
**module-source** (a SQLModel table imported from `app.models` whose canonical home is `app.tables`),
wrong **response/template idiom** (Flask response tuple; no `TemplateResponse`). Seeded from RUN-028 and
**extensible per run** (the same accretion model as the triage anti-flavor catalog / Gap A–AB).
**v0.2 (narrowed): `module_source` detection partly exists** — `WrongImportPathDiagnostic` +
`MisnamedFieldDiagnostic` (`content_contract`, `repair/models.py:128,146`) already flag invented module
specifiers + Prisma field names; reuse/extend them. Net-new detectors are `framework`, `orm_idiom`,
`template_idiom`. Use the rejected `…/generated/app/jobs.py` from RUN-028 as the seed fixture (OQ-7).

### FR-CAR-4 — Deterministic fixes only where unambiguous; escalate the rest
Where a violation has an **unambiguous, contract-grounded** rewrite, repair it **non-destructively**
(revert on break, per existing step discipline): e.g. `session.query(X).get(id)` → `session.get(X, id)`;
import of a known table from the wrong module → its canonical module (when the symbol's home is known from
the contract); alias normalizations. **Wholesale-wrong implementations** (a Flask app, a hand-rolled CRUD
layer) MUST NOT be auto-rewritten — they **escalate** (FR-CAR-6). The safe-fix vs escalate boundary is a
first-class rule (OQ-2), not an ad-hoc per-step choice.

### FR-CAR-5 — Adherence reaches the cheapest tier (micro-prime)
The CKG knowledge-provider's **field-set authority + module-path negatives** MUST be available to (a)
**micro-prime's generation prompt** (`micro_prime/engine.py` `_build_*_prompt`) and (b) the convention
detector/fixer. Net: micro-prime both *generates* and *self-repairs* toward the house style. Closes the
"`micro_prime/` has zero `project_knowledge` refs" gap. (Necessary-but-not-sufficient — adherence.py's own
"injection ≠ adherence" guardrail still applies; pairs with FR-CAR-3 detection.)
**v0.2 (sequenced after FR-CAR-0):** the seam is concrete — add a field to `MicroPrimeContext`
(`micro_prime/context.py:11`), thread it from `gen_context` in `from_prime` (prime_contractor already holds
`self._project_knowledge`), and pass it through `process_file_with_context` → `process_file` → the prompt
builders. Today **nothing project-knowledge-shaped crosses that boundary.** Blocked until FR-CAR-0 yields a
Python authority to inject.

### FR-CAR-6 — Escalate, don't silence (the A3 + symptom-fix guard)
Every diagnostic MUST be classified `repaired` / `safe-unfixable-mechanical` / `convention-or-semantic-unfixable`.
Unfixable `convention`/`semantic` diagnostics MUST be **emitted as escalation** — `EscalationHandoff`
(Keiyaku K-6) in-run, the iterative **residual + verdict** post-run — and **never dropped** (today
`_run_post_generation_repair` returns a count and continues). A pass that fixed a **co-located** mechanical
error (e.g. F811) MUST still surface any residual `convention` violation: **fixing a symptom MUST NOT flip
a FAIL to PASS.**
**v0.2 (made concrete): two model changes are required** — (a) add `unrepaired_diagnostics: List[Diagnostic]`
to `RepairOutcome` (`repair/models.py:278`; today the orchestrator drops them), and (b) add a structured
residual payload to `EscalationHandoff` (`micro_prime/models.py:139`; today only a prose `failure_message`).
Then rewire `prime_adapter._run_post_generation_repair` (returns a bare count today) to escalate on the
residual instead of dropping it.

### FR-CAR-7 — Convention residue is a hard verdict signal
The disk-quality / verdict layer (and the Semantic Compliance Reviewer) MUST treat an **unrepaired
`convention` violation as failing**, even when the file is **lint-clean and AST-valid** (the
wrong-framework-but-clean case). This is the gate-level symptom-fix guard backing FR-CAR-6.
**v0.2 (reframed — feasibility):** appending to `DiskComplianceResult.semantic_issues` is **insufficient** —
`compute_disk_quality_score` (`forward_manifest_validator.py:553`) caps `semantic_penalty` at 0.2 and
hard-zeros only on `ast_valid=False`, so a lint-clean wrong file still scores ~0.8. A **dedicated convention
term** (or a hard-gate: any `error`-severity convention violation → score 0.0, like the `ast_valid` gate) is
required in the formula. Register `convention` as a **distinct** category, not conflated with semantic issues.
This makes the verdict honor the Controlled Corpus's **two-axis** model (structural stability × semantic
compliance): a `false_pass_risk` file — structurally stable but semantically wrong (the Flask RAG, req 0.5) —
MUST score as failing, not ~0.8.

### FR-CAR-8 — Coverage parity with the generators (the lock-step requirement)
As the deterministic generators **expand** (content-pages today; future view / composite generators), the
convention rule set MUST expand **in the same change**: a new owned-artifact kind ships with (a) its
convention rules (FR-CAR-2 source) and (b) a generated-then-corrupted **parity test** (FR-CAR-2). A
generator capability without matching repair coverage is the defect this requirement exists to prevent.
**v0.2 (polyglot scope):** this is **not Python-only.** The existing hand-coded C#/Go/Java convention steps
(`csharp_convention_fix`, `go_dot_import_cleanup`, `java_missing_override`, …) have **no parity tie** to their
generators — they are the drift risk in the present tense. FR-CAR-8 requires bringing them under the same
authority + parity discipline (retro-fit), so all languages share one model rather than N hand-maintained ones.

### FR-CAR-9 — Telemetry + Kaizen feedback
Each convention detection / fix / escalation MUST be logged + OTel-metric'd (`category`, `rule`, `tier`,
`outcome=fixed|escalated`) and routed to **Kaizen**, so recurring **per-tier** convention violations (a)
inform the complexity classifier (postmortem A1 / deterministic-first review **D3** — "SIMPLE + strict
house-style → not micro-prime") and (b) become prompt hints. Convention-fix metrics are pipeline-innate
(system-oriented), matching the existing micro-prime repair metrics.

### FR-CAR-10 — Deterministic, reuse-not-rebuild
The detector and safe-fixers are **deterministic, no-LLM**. Reuse the existing
`Diagnostic`/`RepairContext`/`RepairOutcome`/step-routing (`repair/routing.py`)/`EscalationHandoff`
machinery and the iterative loop's residual concept; add only the `convention` category, the
source-of-truth adapter, the safe fixers, and the **escalate-not-drop** wiring. Same tree → same result.

---

## 4. Non-Requirements

- **Not** a general semantic code-understanding engine. Convention rules are a **bounded, contract-derived**
  catalog, not arbitrary intent inference.
- **Not** auto-rewriting wholesale-wrong implementations (Flask app → FastAPI app). That is **escalation**
  territory (FR-CAR-6), not deterministic repair.
- **Not** the complexity-classifier change itself (A1 / D3). This doc ensures repair + escalation **cover the
  consequence**; routing convention-strict views away from micro-prime is a sibling change.
- **Not** re-implementing the adherence injection. Reuse `project_knowledge`; FR-CAR-5 only **wires it to new
  consumers** (micro-prime + repair).
- **Not** gating-by-default initially. Advisory → gating ramp (the Semantic Compliance Reviewer posture),
  via an env flag, once false-positive rates are measured.
- **Not** in scope: non-Python convention catalogs beyond what each generator already encodes (extend per
  LanguageProfile as those generators mature).

---

## 5. Open Questions

> **v0.2: all seven were resolved by the planning pass — see §0 "Resolved open questions."** Retained
> below as the record of what was asked (per the reflective-loop discipline: modify, don't delete).

- **OQ-1 — Source of truth.** Which artifact authoritatively encodes framework/ORM/module-source house
  style — `project_knowledge` (CKG), the `LanguageProfile`, or a new shared convention manifest? How much is
  per-project (module-source) vs per-language (framework/ORM)? (FR-CAR-2 hinges on this.)
- **OQ-2 — Safe-fix vs escalate boundary.** Formalize "deterministically rewritable": AST-local + single-symbol
  + contract-grounded? What's the test that keeps a fixer from a destructive rewrite (FR-CAR-4)?
- **OQ-3 — In-run vs post-run homes.** Does convention-repair live in micro-prime's element pipeline
  (`EscalationHandoff` K-6), the post-run iterative loop (residual), the Semantic Compliance Reviewer, or
  all three — and how do they share one rule set without divergence?
- **OQ-4 — Relationship to existing categories.** Extend the existing `semantic` / `contract_violation`
  Diagnostic categories and the in-run `MicroPrimeConfig.semantic_verification_*` (default-on), or add
  `convention` as distinct? Avoid overlap/double-counting with `disk_compliance.semantic_issues`.
- **OQ-5 — Cross-tier scope.** Run convention-repair for **all** tiers, or gate to cheap/micro-prime where
  adherence is weakest (cost)? The CKG data shows the largest lift on the cheapest tier.
- **OQ-6 — Symptom-fix linkage.** How does FR-CAR-6 concretely link a mechanical fix (F811) to a co-located
  convention residue — same file? same element? same import cluster? — to flag "you fixed a symptom" without
  false positives?
- **OQ-7 — Bootstrap corpus.** Is RUN-028's rejected `jobs.py` (and prior run residues) available as the
  seed corpus for the FR-CAR-2 parity tests and FR-CAR-3 detector fixtures?

---

*v0.2 — Post-planning self-reflective update. 1 requirement **added** (FR-CAR-0, foundational: the Python
convention source-of-truth doesn't exist yet); 4 **narrowed** to reuse existing machinery (FR-CAR-1 convention
category already exists for C#; FR-CAR-3 `module_source` partly exists as `content_contract`; FR-CAR-2/5 keyed
to FR-CAR-0); 2 **reframed for feasibility** (FR-CAR-6 needs 2 model fields; FR-CAR-7 needs a dedicated verdict
term, not `semantic_issues`); 7 open questions resolved. Net: the work is mostly **extending established
patterns**, gated on building the Python convention authority first.*

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
