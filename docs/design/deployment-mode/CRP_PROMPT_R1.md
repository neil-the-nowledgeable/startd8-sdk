# Convergent Review Prompt

**Generated:** 2026-06-11 17:55:56 UTC
**Mode:** Dual-Document (Plan + Requirements)

> **For the human / orchestrator who generated this file (not instructions to the reviewing agent):**
>
> - This prompt asks the reviewing **agent** to **persist suggestions directly into the source documents** by appending a new **Review Round** under the document's **Appendix C (Incoming)**. The A/B/C scaffold is **pre-initialized by this generator script** (per `CONVERGENT_REVIEW_AGENT_GUIDE.md`), so the reviewer only appends. The chat reply is a short write-confirmation only — **no** in-chat numbered list.
> - **Triage is yours and MUST be persisted, not stripped:** for each suggestion record a disposition — **Accepted → Appendix A** (note where it was merged) or **Rejected → Appendix B** (with rationale) — and update the **Areas Substantially Addressed** tracker (3 accepted per area). Appendices A/B are the **cross-model memory**: later reviewers (you embed the guide telling them so) read them to avoid re-proposing settled or rejected ideas. Do **not** delete A/B after merging.
> - **Suggested separate review passes (orchestrator workflow):** 1 — e.g. run the prompt once for breadth, again for adversarial pass, then triage yourself.
> - **Triage threshold (reference):** 3 accepted suggestions per review area when you triage.
> - **Max suggestions to request from the model:** 10 (soft cap in reviewer instructions below).
> - **Reviewer must have file-write tools (Write/Edit/equivalent) and filesystem access to the source documents.** Chat-only LLMs will fail this contract.

### Source documents

| Role | Path | Size |
|------|------|------|
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deployment-mode/DEPLOYMENT_MODE_PLAN.md` | 158 lines · 1974 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deployment-mode/DEPLOYMENT_MODE_REQUIREMENTS.md` | 330 lines · 3461 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deployment-mode/CRP_FOCUS_R1.md` | 23 lines · 256 words |

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

# CRP R1 — Where we need input most

Weight the review on these three load-bearing boundaries (over generic completeness nits):

1. **Determinism spine.** The design bets that `app/settings.py` is the *single* generated file whose
   bytes vary by mode, with `db.py`/`main.py` reading it at runtime so they stay byte-identical across
   modes. Critically: the backend drift/skip-hook (`provider.py:is_in_sync`) is **schema-only** — it
   reads `schema.prisma`, never `app.yaml`. If mode lives in `app.yaml` and bakes into `settings.py`,
   how does the drift checker re-derive mode to verify `settings.py` is in-sync? Is the spine actually
   sound, or does it force `app.yaml` into the backend drift input set (and if so, is that acknowledged
   and scoped)? Pressure-test FR-CFG-7, FR-DET-1/2/3, and Plan D1/Step A2/A9.

2. **Security topology.** Is the deployed-mode auth **seam** (`get_principal` + `require_principal`,
   no credential store) + **deferred** Tier-B tenant isolation architecturally safe? Specifically: can
   a deployed app ship *without* tenant scoping (M2 before M3) and create a false sense of multi-user
   safety? Should deployed mode without a tenant declaration be a coherence error, a loud warning, or
   fine? Does the bucket-1 (mechanism) / bucket-4 (policy) fence actually hold for auth, or does
   "reference scaffold, not production" leave an unsafe default? Pressure-test FR-IDN-2/3, FR-TEN-*, NR-1.

3. **Coherence guard semantics.** FR-CFG-5 rejects incoherent mode × DSN × migrations combos. Are the
   rules complete and unambiguous? e.g. `installed` + Postgres DSN, `deployed` + SQLite file DSN,
   `deployed` + `migrations:false`. What about `deployed` + loopback bind, or env `STARTD8_DEPLOYMENT_MODE`
   disagreeing with the baked constant at runtime (FR-CFG-4) — warn vs refuse? Pressure-test FR-CFG-4/5, Step A7.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deployment-mode/DEPLOYMENT_MODE_PLAN.md`  ·  **Size:** 158 lines · 1974 words

```markdown
# Deployment Mode (Installed vs Deployed) — Implementation Plan

**Version:** 1.0 (Draft — discoveries fed back into Requirements v0.2 §0)
**Date:** 2026-06-11
**Status:** Draft
**Pairs with:** `DEPLOYMENT_MODE_REQUIREMENTS.md` v0.2

> This plan stress-tests the requirements by mapping each to real files. Discoveries that contradict
> or simplify the requirements are captured in §1 and flow back into Requirements v0.2 (§0).

---

## 1. Planning Discoveries (feed Requirements §0)

| # | Requirements v0.1 assumed | Planning revealed | Impact on requirements |
|---|---------------------------|-------------------|------------------------|
| D1 | Mode is a generation input hashed into many artifacts (FR-DET-1, FR-CFG-3a) | The backend **drift/skip-hook path is schema-only**: `provider.py:is_in_sync` reads `schema.prisma`, never `app.yaml`; `render_db`/`render_main` take `(schema_text, source_file)` only. Threading mode into backend bytes means widening the drift input set (like `completeness_text`/`forms_text`/`display_text` already do via the `_renderers()` closure) **and** teaching the provider + `--check` to read `app.yaml`. Non-trivial cross-cut. | Minimize byte-affecting mode surface. Prefer runtime env reads inside already-emitted files over new generation inputs wherever security doesn't require baking. |
| D2 | `main.py` would change shape by mode (bind, layers) | `render_main` is **deliberately frozen**: every optional layer (AI, pages, flows, polish, `user_routers`) mounts via a **tolerant `try/except ModuleNotFoundError` import** so main.py's drift hash never moves. This is the idiomatic extension seam. | Add deployed-mode layers (auth, tenancy middleware) the **same way** — as new optional modules main.py already tolerantly imports — so main.py stays byte-identical. Don't rewrite main.py per mode. |
| D3 | Persistence needs structural divergence for Postgres (FR-PER-2) | `render_db` **already** runtime-branches `if engine.dialect.name == "sqlite"` for pragmas and works against Postgres today via `DATABASE_URL`. The only deployed gaps are (a) pool config and (b) not auto-`create_all`. | FR-PER-2 is largely **overspecified** — persistence is already mode-agnostic at runtime. Narrow to: pool sizing + create_all gate, both achievable as **runtime env reads inside db.py** (near-zero drift). |
| D4 | Migration-vs-createall is structural (FR-PER-3) | `init_db()` is called from main.py's frozen lifespan; gating it by reading mode **inside db.py** keeps main.py byte-identical and adds one env-conditional branch to db.py. | Reclassify FR-PER-3 as a **runtime binding** (FR-CFG-3b) with a mode-derived default, not structural. |
| D5 | Bind host is structural-ish (FR-NET-1) | Bind is set by the run command (uvicorn CLI / Dockerfile), not by app code. | FR-NET-1 default is emitted into the **run command / Dockerfile** (scaffold), and/or a `settings.py` default — runtime binding, mode-derived default. |
| D6 | One `deployment.mode` could subsume OTel `deployment_environment` (OQ-5) | They are **orthogonal axes**: mode = topology/security shape (installed/deployed); environment = telemetry tag (dev/staging/prod). installed+dev and deployed+prod both valid. | Keep separate; mode sets a default for the OTel tag but does not replace it. |
| D7 | Deterministic auth mechanism is shippable at $0 (FR-IDN-2, OQ-3) | Rolling a real credential/session system deterministically is a **security liability** to ship naively. The repo's idiom is the `user_routers.py` **seam**. | Narrow FR-IDN-2: deployed mode emits a **principal-resolution dependency + a `require_principal` guard + the seam + a reference (non-production) scaffold**, NOT a credential store. Real auth = operator (bucket 4). |
| D8 | Tenant scoping is "part of the generated code shape" (FR-TEN-2/3) | True structural item: it changes **router query bodies** (`select(E)` → `select(E).where(E.owner == principal)`), per-entity templates, and smoke tests. This is the **only large-blast-radius** dimension and needs the schema to declare the owner relationship (OQ-2). | Split into a **second increment (Tier B)**; v1 pilot defers tenancy. Require explicit `deployment.tenant` declaration; **no silent owner-column synthesis** (it would mutate the human-owned schema contract). |
| D9 | A runtime "mode signal" is enough (FR-CFG-4) | There is **no settings/config module** emitted today; several env reads (mode, pool, create_all gate, bind default) want one home. | **Add a requirement**: emit a small owned `app/settings.py` centralizing mode + env reads (new owned `$0.00-skip` kind). |
| D10 | `migrations.enabled` vs mode (OQ-6) | `AppManifest.migrations: bool` already exists and drives Alembic emission in scaffold_codegen. | Mode sets the **default** for migrations; the coherence guard (FR-CFG-5) reconciles explicit conflicts (`deployed` + `migrations:false` → error/warn). Keep fields independent. |

**Net:** the byte-affecting (generation-time) surface is far smaller than v0.1 implied. Two tiers emerge:

- **Tier A (v1 pilot) — low blast radius, mostly runtime:** mode declaration + `settings.py` + db.py pool/create_all gate + bind/Dockerfile default + secrets/OTel default + coherence guard + wireframe surfacing + auth *seam scaffold* (optional module).
- **Tier B (increment 2) — high blast radius, structural:** tenant-scoped queries in routers/templates/tests; requires `deployment.tenant` declaration. Deferred.

This is the reflective loop working: >30% of the v0.1 requirements get reclassified or narrowed (D3, D4, D5, D7, D8) — confirming they were premature.

---

## 2. Architecture of the Change

```
app.yaml  deployment: { mode: installed|deployed, tenant?: {...} }   (Tier B uses tenant)
   │
   ├─ scaffold_codegen/manifest.py  ── AppManifest.deployment_mode (new field) ──┐
   │                                                                             │
   ├─ generate backend ── coherence guard (mode × DSN × migrations) ── fail-fast │
   │                                                                             ▼
   └─ backend_codegen ──► emits owned app/settings.py  (mode constant + env reads)
                          │
                          ├─ db.py reads settings: pool sizing + create_all gate  (runtime)
                          ├─ main.py UNCHANGED (tolerant import of optional app/auth.py seam)
                          ├─ Dockerfile/run default bind from mode                 (scaffold)
                          └─ (Tier B) routers/templates/tests gain tenant scoping  (deferred)
```

Guiding principle from D1/D2: **bake only what security requires; bind everything else at runtime.**

---

## 3. Work Breakdown — Tier A (v1 pilot)

### Step A1 — Mode declaration & manifest (FR-CFG-1/2)
- `scaffold_codegen/manifest.py`: add `deployment` to `_TOP_KEYS`; add `AppManifest.deployment_mode: str = "installed"`; parse `data["deployment"]["mode"]`, validate enum, strict on unknown keys.
- Add a tiny shared `deployment_mode` accessor usable by both scaffold and backend codegen (avoid scatter — FR-CFG-2).

### Step A2 — Owned `app/settings.py` (FR-CFG-4, D9)
- New renderer `render_settings()` in `backend_codegen` → `app/settings.py` (new owned kind `python-settings`).
- Emits: `DEPLOYMENT_MODE = "<baked from app.yaml>"` constant + helpers that read env (`STARTD8_DEPLOYMENT_MODE` for *validation only*, `DATABASE_URL`, pool size, bind default).
- This file **does** vary by mode → it is the one new generation input that must be drift-hashed. Resolve D1 by passing the mode into this single renderer and registering it in `drift._renderers()`.
- FR-CFG-4 validation: on startup, if env `STARTD8_DEPLOYMENT_MODE` disagrees with baked `DEPLOYMENT_MODE`, log a loud warning / refuse (never silently switch structural shape).

### Step A3 — db.py persistence posture (FR-PER-1/2/3, FR-CON-1, D3/D4)
- `render_db()`: import from `.settings`; keep SQLite pragmas under the existing dialect branch; add pool args when deployed (runtime read); gate `create_all` in `init_db()` so deployed does NOT auto-create against shared DB (loud "run alembic upgrade head" instead).
- db.py gains mode-awareness via **runtime env read**, not a new generation input → **zero drift** for db.py if written to read settings at runtime. (Decision point: settings constant is baked, db.py reads it at runtime → db.py bytes unchanged by mode. Prefer this.)

### Step A4 — Bind default & container shape (FR-NET-1/2, D5)
- `scaffold_codegen/renderers.py:render_dockerfile()`: bind `127.0.0.1` vs `0.0.0.0` from `manifest.deployment_mode`; for installed, emit a local run script (`run.sh`/console entry) instead of presenting a public-server container as primary.
- Mode → Dockerfile bytes change → scaffold drift already hashes the manifest, so this is consistent with existing scaffold drift (manifest SHA in header). Verify.

### Step A5 — Secrets & observability defaults (FR-SEC-1, FR-OBS-1, D6)
- Tie mode to the **default** secrets backend (`local` vs expect `doppler`) and OTel posture, reusing the existing `secrets/` switch — mode only changes the default, never overrides explicit operator config. Keep `deployment.mode` orthogonal to OTel `deployment_environment`; set default, don't subsume.

### Step A6 — Auth seam scaffold (FR-IDN-1/2/3, D7)
- Installed: nothing emitted (today's behavior).
- Deployed: emit optional `app/auth.py` (new owned kind `python-auth-seam`) providing a `get_principal` dependency + `require_principal` guard wired to the existing `user_routers.py` seam — a **reference scaffold**, clearly marked not-production, policy left to operator. main.py tolerantly imports it (D2) → main.py unchanged.

### Step A7 — Coherence guard (FR-CFG-5, D10)
- In `generate backend` (and `wireframe`): reject/refuse incoherent combos — `installed` + Postgres DSN + no shared posture; `deployed` + SQLite file DSN; `deployed` + `migrations:false`. Clear messages.

### Step A8 — Wireframe surfacing (FR-CFG-6, FR-CLI-2)
- `startd8 wireframe`: print declared mode + resolved per-dimension posture (persistence/bind/auth/secrets/observability) and any coherence warnings. $0, read-only.

### Step A9 — Drift, gates, tests (FR-DET-1..4)
- Register `python-settings` (and `python-auth-seam` when deployed) in `provider.py` owned kinds + `drift._renderers()`.
- Extend `gates.py`: assert settings.py mode constant matches app.yaml; assert deployed emits auth seam.
- Tests: idempotency per mode (installed byte-identical to today = regression guard; deployed in_sync); coherence-guard failures; wireframe output.

## 4. Work Breakdown — Tier B (increment 2, deferred)

### Step B1 — Tenant declaration (OQ-2)
- `deployment.tenant: { model: User, owner_field: owner_id }` in app.yaml; validate the referenced model/field exist in the schema; **no synthesis**.

### Step B2 — Scoped queries (FR-TEN-2/3, D8)
- `render_routers()` + per-entity htmx templates: thread an owner predicate into list/detail/update/delete query paths via the principal dependency.
- This widens the backend drift input set to include `tenant` config → follow the `completeness_text` threading precedent in `_renderers()`.

### Step B3 — Isolation tests (FR-TEN-3)
- Extend route smoke/contract tests: a cross-principal read MUST be denied.

---

## 5. Sequencing & Milestones

1. **M0 — manifest + settings + regression** (A1, A2, A9-regression): mode declared, `installed` output byte-identical to today, `deployed` emits settings.py. Proves the determinism spine.
2. **M1 — operational posture** (A3, A4, A5, A7, A8): persistence/bind/secrets/observability defaults + coherence guard + wireframe. The "operationally deployable" slice, almost all runtime.
3. **M2 — auth seam** (A6): deployed-mode auth scaffold + seam.
4. **M3 (later) — Tier B tenancy** (B1–B3): the one heavy structural increment, behind explicit declaration.

Pilot recommendation (OQ-7): ship **M0+M1** as the deterministic v1 pilot on `backend_codegen`; M2 close behind; M3 separately.

---

## 6. Risks

- **R1 — Drift input widening (D1).** Teaching the backend drift/skip-hook to read `app.yaml` for the one mode-varying file (settings.py) is the riskiest cross-cut; mitigate by keeping settings.py the *only* byte-varying file and having db.py/main.py read it at runtime.
- **R2 — Shipping insecure auth (D7).** Mitigate by scaffolding a seam, not a credential store; mark non-production; lean on `user_routers.py`.
- **R3 — Tenancy correctness (D8).** Server-side enforcement + denial tests; defer to M3 so v1 isn't blocked.
- **R4 — Installed regression.** M0 must prove `installed` == today byte-for-byte before anything else.

---

*Plan v1.0 — paired with Requirements v0.1. Discoveries D1–D10 feed Requirements §0 (v0.2).*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/deployment-mode/DEPLOYMENT_MODE_REQUIREMENTS.md`  ·  **Size:** 330 lines · 3461 words

```markdown
# Deployment Mode (Installed vs Deployed) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-06-11
**Status:** Draft
**Owner:** StartD8 SDK / backend_codegen (bucket-1, $0 deterministic)
**Pilot surface:** Apps generated by `startd8 generate backend` (the `backend_codegen` path)

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass (see `DEPLOYMENT_MODE_PLAN.md` §1, discoveries D1–D10) mapped every requirement to
> real files and reclassified five of them. The central lesson: **the byte-affecting (generation-time)
> surface is far smaller than v0.1 assumed.** Most "deployed" behavior is achievable as runtime env
> reads inside files the generator *already* emits — so determinism/drift risk shrinks dramatically.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Mode is a generation input hashed into many artifacts | Backend drift/skip-hook is **schema-only** (`provider.py:is_in_sync` never reads `app.yaml`; `render_db`/`render_main` take `(schema_text, source_file)`). Widening it is the real cost. | Bake **only** what security requires; bind everything else at runtime. Keep the byte-varying surface to **one** new file (`app/settings.py`). |
| `main.py` changes shape by mode | `render_main` is deliberately **drift-frozen**; all layers mount via tolerant `try/except ModuleNotFoundError` imports. | Add deployed layers (auth seam) the same way → main.py stays byte-identical. |
| Postgres needs structural divergence (FR-PER-2) | `db.py` **already** runtime-branches on dialect and works against Postgres via `DATABASE_URL`. | FR-PER-2 **narrowed**: only pool sizing + create_all gate remain, both runtime. |
| Migration-vs-createall is structural (FR-PER-3) | Gating `init_db()` via a settings/env read keeps main.py frozen. | FR-PER-3 **reclassified** to a runtime binding with a mode-derived default. |
| Deterministic auth mechanism is shippable (FR-IDN-2) | Rolling a credential/session store deterministically is a security liability; repo idiom is the `user_routers.py` seam. | FR-IDN-2 **narrowed** to a principal-resolution dependency + `require_principal` guard + reference seam scaffold (not a credential store). |
| Tenant scoping is just "the generated shape" (FR-TEN-2/3) | It's the **only** large-blast-radius item: changes router query bodies, templates, tests; needs an explicit owner declaration. | FR-TEN-* **split to a deferred Tier B increment**; v1 pilot defers tenancy; **no silent owner-column synthesis**. |
| A runtime "mode signal" suffices (FR-CFG-4) | No settings module exists today; several env reads want one home. | **New requirement FR-CFG-7**: emit an owned `app/settings.py`. |

**Resolved open questions:**
- **OQ-1 → Additive optional layers, not divergent rewrites.** Deployed behavior is added as new optional modules (tolerant-import seam) + runtime env reads; only `app/settings.py` varies by mode in generated bytes.
- **OQ-2 → Explicit declaration, no synthesis.** Tenancy requires a declared `deployment.tenant` block validated against the schema; the SDK never mutates the human-owned schema contract to add an owner column. (Tier B.)
- **OQ-3 → Mechanism-seam, not a credential store.** Deployed auth = principal dependency + guard + reference scaffold via `user_routers.py`; real auth policy is operator content (bucket 4).
- **OQ-4 → Two tiers.** Tier A blast radius = one new file (`settings.py`) + an optional `auth.py` + a scaffold Dockerfile change. Tier B (tenancy) touches routers + per-entity templates + tests.
- **OQ-5 → Orthogonal axes.** `deployment.mode` (topology/security) is independent of OTel `deployment_environment` (telemetry tag). Mode sets a default for the tag; it does not subsume it.
- **OQ-6 → Mode drives the default, guard reconciles conflicts.** Existing `AppManifest.migrations` and the new `deployment.mode` stay independent fields; the coherence guard (FR-CFG-5) errors on `deployed` + `migrations:false`.
- **OQ-7 → Pilot = M0+M1 (operational posture), auth M2, tenancy M3.** Ship the runtime-light slice first; defer the one heavy structural increment.

---

## 1. Problem Statement

A StartDate app generated deterministically from one `schema.prisma` contract today has exactly
one runtime shape: **single-user, local-first**. It binds (via uvicorn) to a host the operator
passes, persists to a SQLite file (`DATABASE_URL` env, default `sqlite:///./app.db`), has **no
identity/auth/tenancy layer** (every route is public, no user column, no row scoping), initializes
its schema with `create_all` on startup, and logs to a local file. This is correct for an app a
person **installs on their own computer** and uses alone.

It is **wrong** for an app **deployed to shared compute serving many users**, where the same
process and the same database are shared across tenants. There, the app needs authenticated
identity, per-user/tenant data isolation, a concurrency-safe shared database (Postgres, not a
single-writer SQLite file), managed migrations rather than `create_all`, a non-loopback bind, and
centralized observability. Generating one shape and asking operators to bolt the other on by hand
defeats the determinism thesis (bucket 1): the *application skeleton* for "who can see what" and
"where does data live" is structural, not content, and should be generated, not hand-written.

We need a **deployment mode** capability: a first-class, declared choice — **installed** vs
**deployed** — that governs both (a) the **configuration surface** by which a build/app declares and
switches mode, and (b) the **underlying behavioral differences** across persistence, identity,
tenancy, concurrency, networking, config/secrets, data lifecycle, and observability. The capability
must hold the line on determinism: same inputs (including mode) → byte-identical output, drift-checkable.

### Current-state gap table

| Dimension | Installed need (single-user, local) | Deployed need (multi-user, shared) | Current state | Gap |
|-----------|-------------------------------------|------------------------------------|---------------|-----|
| **Mode declaration** | implicit | implicit | none — no `mode` concept | No declared mode anywhere |
| **Persistence** | SQLite file, WAL | shared Postgres, pooled | SQLite default, `DATABASE_URL` env override only | No dialect/mode awareness; pragmas SQLite-only |
| **Schema init** | `create_all` fine | managed migrations (Alembic) | `create_all` on startup always | No migration-vs-createall mode gate |
| **Identity / auth** | implicit single owner | authenticated users + sessions | none (all routes public) | Entire auth layer absent |
| **Tenancy / isolation** | n/a (one user owns all) | per-user/tenant row scoping | none (global queries) | No owner/tenant scoping in queries |
| **Concurrency** | one writer | many concurrent requests | SQLite single-writer + WAL | No pool/locking strategy for shared DB |
| **Networking / bind** | loopback `127.0.0.1` | container `0.0.0.0` | uvicorn CLI / Dockerfile `0.0.0.0:8000` | Bind not mode-derived; Dockerfile always server-shaped |
| **Config / secrets** | local file / OS keychain | env + secrets manager (Doppler) | `secrets/` backend exists, off by default | Not tied to mode; no per-mode default |
| **Data lifecycle** | local file backup/export | migrations, backups, retention | `export.py` + optional Alembic | No deployed-grade lifecycle posture |
| **Observability** | local file logs | centralized OTel/Loki | local rotating file logs; OTel `deployment.environment` tag exists but behavioral-only | No mode→telemetry posture link |

---

## 2. Goals & Non-Goals (summary)

**Goal:** Make "installed vs deployed" a declared, deterministic, drift-checkable property of a
generated app that coherently governs the eight behavioral dimensions, piloted on `backend_codegen`.

**Primary non-goal (see §7):** This capability generates the **mechanism** (the structural skeleton
for identity, isolation, persistence posture) — bucket 1. It does **not** author security **policy**
content (which IdP, password rules, retention durations) — that is operator/company input (bucket 4).

---

## 3. Requirements

### 3.A Configuration & Mode Declaration

- **FR-CFG-1 (Declared mode).** A generated app's deployment mode SHALL be a declared enum
  `installed | deployed`, authored in `app.yaml` under a top-level `deployment:` block
  (e.g. `deployment.mode: installed`). `installed` is the default when unspecified (preserves
  today's behavior and the "off by default" precedent of the secrets backend).
- **FR-CFG-2 (Single source of truth).** Mode SHALL be parsed into the `AppManifest` (scaffold) /
  the backend generation inputs as a typed field; emitters MUST read it from one place, not
  re-derive it. No scattered mode literals.
- **FR-CFG-3 (Generation-time vs runtime split).** The capability SHALL distinguish:
  (a) **structural** behaviors that change emitted bytes (auth layer present/absent, tenant scoping
  in queries, migration vs `create_all`, Dockerfile shape) — these are a **generation input**; and
  (b) **binding** behaviors that don't change bytes (DB URL, bind host, secrets backend, log sink) —
  these stay **runtime env-driven**. The requirements MUST classify each dimension as (a) or (b).
- **FR-CFG-4 (Runtime mode signal).** The generated app SHALL expose its compiled-in mode at runtime
  (e.g. a `DEPLOYMENT_MODE` constant / settings value) and SHALL read a single env var
  `STARTD8_DEPLOYMENT_MODE` only to *validate* (warn/refuse) that the runtime environment matches the
  generated shape — it MUST NOT silently switch structural behavior the code wasn't generated for.
- **FR-CFG-5 (Mode coherence guard).** A build SHALL fail fast (clear error) on incoherent
  combinations — e.g. `mode: installed` + multi-user auth requested, or `mode: deployed` + a SQLite
  file DSN with no shared-DB posture. Incoherence is a build error, not a runtime surprise.
- **FR-CFG-6 (Wireframe/preflight visibility).** `startd8 wireframe` SHALL report the declared mode
  and the resulting per-dimension posture before generation ($0, read-only advisory), so the operator
  sees what the mode will build.
- **FR-CFG-7 (Emitted settings module — added v0.2, D9).** The backend SHALL emit one owned
  `app/settings.py` that bakes the mode constant (`DEPLOYMENT_MODE`) and centralizes the runtime env
  reads (DB URL, pool size, bind default, create_all gate). This is the **single** file whose
  generated bytes vary by mode; `db.py` and `main.py` read it at runtime and stay byte-identical
  across modes. Registered as a new `$0.00-skip` owned kind (`python-settings`).

### 3.B Persistence

- **FR-PER-1 (Installed persistence).** In `installed` mode the app SHALL default to SQLite with WAL
  + busy_timeout pragmas at a local file path (today's behavior), suitable for a single user.
- **FR-PER-2 (Deployed persistence — narrowed v0.2, D3).** `db.py` *already* runtime-branches on
  dialect and works against Postgres via `DATABASE_URL` (pragmas already gated to SQLite). The only
  deployed-specific gaps are (a) connection-pool sizing and (b) the create_all gate (FR-PER-3). Both
  SHALL be **runtime env reads** sourced from `app/settings.py` (FR-CFG-7), not a structurally
  divergent db.py. The DSN stays a runtime binding. *(No new generation input; near-zero drift.)*
- **FR-PER-3 (Schema init posture — reclassified v0.2, D4).** The `init_db()` create_all call SHALL
  be **gated at runtime** by the mode in `app/settings.py`: `installed` may `create_all` on startup;
  `deployed` SHALL NOT auto-`create_all` against a shared DB and SHALL instead rely on managed
  migrations (Alembic, already emitted by `scaffold_codegen`), warning loudly if the live schema
  drifts. This is a runtime binding (FR-CFG-3b) with a mode-derived default — `main.py` stays frozen.

### 3.C Identity & Authentication

- **FR-IDN-1 (Installed identity).** In `installed` mode the app SHALL operate as an implicit single
  owner — no login, no auth layer emitted (today's behavior).
- **FR-IDN-2 (Deployed identity — narrowed v0.2, D7).** In `deployed` mode the app SHALL emit an
  optional `app/auth.py` (owned kind `python-auth-seam`) providing a **principal-resolution
  dependency** (`get_principal`) and a **`require_principal` guard**, wired to the existing
  project-owned `user_routers.py` seam and mounted via `main.py`'s tolerant optional-import (so
  `main.py` stays byte-identical, D2). This is a **reference seam scaffold, explicitly marked
  not-production** — it is NOT a credential/session store. Building/rolling a real credential system
  deterministically is out of scope (a security liability); the credential backend and login policy
  are operator content (bucket 4, FR-IDN-3).
- **FR-IDN-3 (Policy is not generated).** The generated auth mechanism SHALL leave the **policy**
  (which IdP/OAuth provider, password rules, MFA) as configuration/extension seams (e.g. the existing
  project-owned `user_routers.py` seam), NOT hard-authored. (Bucket boundary — see §7.)

### 3.D Tenancy & Data Isolation — **DEFERRED to Tier B / increment M3 (v0.2, D8/OQ-4)**

> Planning showed tenancy is the **only** large-blast-radius dimension (it changes router query
> bodies, per-entity templates, and tests, and widens the backend drift input set). It is split out
> so the v1 pilot (M0+M1) is not blocked. These requirements stand but are **not in the v1 scope**.

- **FR-TEN-1 (Installed isolation).** In `installed` mode there is no tenancy; all data belongs to
  the single owner; queries are unscoped (today's behavior). *(Holds in v1 — installed is the default.)*
- **FR-TEN-2 (Deployed isolation — Tier B).** In `deployed` mode, where the schema declares an
  owner/tenant relationship via an **explicit** `deployment.tenant: { model, owner_field }` block
  (validated against the schema — **no silent owner-column synthesis**, OQ-2), generated
  CRUD/list/detail queries SHALL be scoped to the current principal so users cannot read or mutate
  other users' rows. Isolation SHALL be enforced server-side in the generated query path, not by UI
  omission.
- **FR-TEN-3 (Isolation is structural — Tier B).** Tenant scoping SHALL be part of the generated code
  shape (generation-time/structural per FR-CFG-3a), threaded into the backend drift input set
  following the `completeness_text`/`forms_text` precedent, and MUST be reflected in the generated
  route smoke/contract tests (a cross-principal read MUST be denied).

### 3.E Concurrency

- **FR-CON-1.** `installed` mode assumes a single concurrent writer; `deployed` mode SHALL generate
  engine/session configuration safe for many concurrent requests against the shared DB (connection
  pool, no reliance on SQLite single-writer semantics).

### 3.F Networking / Bind

- **FR-NET-1 (Bind default by mode — clarified v0.2, D5).** Bind host is set by the run command
  (uvicorn CLI / Dockerfile), not by app code. Its **default** SHALL be mode-derived — `installed` →
  loopback `127.0.0.1`, `deployed` → `0.0.0.0` — emitted into the generated run command / Dockerfile
  (scaffold) and surfaced via `app/settings.py`. Runtime binding (FR-CFG-3b); no app-code structural change.
- **FR-NET-2 (Container shape).** The generated Dockerfile/run posture SHALL match mode: `deployed`
  emits the server container (today's `0.0.0.0:8000`); `installed` SHALL NOT present a public-server
  container as the primary run path (it MAY emit a local run script / desktop-launch entrypoint).

### 3.G Config & Secrets

- **FR-SEC-1.** Mode SHALL set the **default** secrets posture: `installed` defaults to the local
  secrets backend (file / OS-level); `deployed` defaults to an external secrets manager backend
  (Doppler) being expected. This reuses the existing `secrets/` backend switch; mode only changes the
  default, never overrides an explicit operator choice. (Runtime binding per FR-CFG-3b.)

### 3.H Data Lifecycle

- **FR-DAT-1.** `installed` lifecycle = local file persistence + the existing `export.py` for
  backup/portability. `deployed` lifecycle = migration-managed schema evolution (Alembic) plus
  documented seams for backup/retention (the durations/retention policy itself is operator content,
  bucket 4).

### 3.I Observability

- **FR-OBS-1.** Mode SHALL set the **default** observability posture: `installed` → local rotating
  file logs (today's behavior), `deployed` → OTel/centralized export expected, and the OTel
  `deployment.environment` resource attribute SHALL be aligned with mode rather than diverging from it.

### 3.J Determinism & Drift Integration (cross-cutting)

- **FR-DET-1 (Mode is a hashed input).** Any generated bytes that differ by mode SHALL treat mode as
  a generation input hashed into the artifact header, so `--check` drift detects a mode change exactly
  as it detects a schema change. No mode-dependent output may be invisible to drift.
- **FR-DET-2 (Idempotency per mode).** For a fixed (schema, app.yaml, mode) tuple, generation SHALL
  be byte-identical and `--check` SHALL report `in_sync` (exit 0).
- **FR-DET-3 (New owned kinds registered).** Any new emitted file kinds (e.g. auth mechanism, tenant
  scoping helpers) SHALL be registered as `$0.00-skip` owned kinds in `provider.py` and in
  `drift._renderers()`, consistent with the existing ~12 owned kinds.
- **FR-DET-4 (Gates extended).** Quality gates (`gates.py`) SHALL be extended so deployed-mode
  structural guarantees (e.g. every entity route carries tenant scoping when the schema declares an
  owner) are verified at generation time, not merely at runtime.

### 3.K CLI / Tooling

- **FR-CLI-1.** `startd8 generate backend` SHALL honor the declared mode with no new flag required
  (mode comes from `app.yaml`); an optional `--mode` override MAY exist for ergonomics but `app.yaml`
  is the source of truth for drift.
- **FR-CLI-2.** `startd8 wireframe` SHALL surface mode + posture (FR-CFG-6).

---

## 4. Non-Requirements (explicit scope fence)

- **NR-1.** NOT authoring real auth policy (IdP choice, password/MFA rules) — mechanism only (bucket 4 boundary).
- **NR-2.** NOT a third "hybrid"/auto-detecting mode in v1 — exactly two declared modes.
- **NR-3.** NOT runtime hot-switching of structural shape — an installed app does not become multi-user by flipping an env var (FR-CFG-4).
- **NR-4.** NOT desktop packaging (PyInstaller/Electron/single-binary) in v1 — `installed` means a local-run Python app, not a shipped binary.
- **NR-5.** NOT database migration *authoring*/data migration — only the createall-vs-Alembic posture gate.
- **NR-6.** NOT extending this to the Artisan path (ON HOLD) or non-`backend_codegen` generators in v1.
- **NR-7.** NOT building Postgres provisioning/ops — generating code that *targets* Postgres ≠ standing up Postgres.
- **NR-8.** NOT inventing a client framework — server-rendered HTMX shape is preserved (per IDEAL_TARGET_ARCHITECTURE.md).

---

## 5. Open Questions — **ALL RESOLVED in planning (see §0 and `DEPLOYMENT_MODE_PLAN.md` §1)**

- **OQ-1 → RESOLVED: additive optional layers, not divergent rewrites.** Only `app/settings.py`
  varies by mode in generated bytes; deployed adds optional modules via the tolerant-import seam + runtime env reads.
- **OQ-2 → RESOLVED: explicit `deployment.tenant` declaration, no synthesis.** The SDK never mutates the
  human-owned schema contract to add an owner column. (Tier B.)
- **OQ-3 → RESOLVED: mechanism-seam, not a credential store.** Deployed auth = principal dependency +
  guard + reference scaffold; real auth is operator content (bucket 4).
- **OQ-4 → RESOLVED: two tiers.** Tier A = `settings.py` + optional `auth.py` + a scaffold Dockerfile
  change. Tier B (tenancy) = routers + per-entity templates + tests.
- **OQ-5 → RESOLVED: orthogonal axes.** `deployment.mode` (topology/security) ≠ OTel
  `deployment.environment` (telemetry tag); mode sets a default for the tag, does not subsume it.
- **OQ-6 → RESOLVED: independent fields, guard reconciles.** Mode sets the migrations default; FR-CFG-5
  errors on `deployed` + `migrations:false`.
- **OQ-7 → RESOLVED: pilot = M0+M1** (manifest+settings+regression, then operational posture); auth M2;
  tenancy M3. See `DEPLOYMENT_MODE_PLAN.md` §5.

---

## 6. Acceptance (provisional)

- A `schema.prisma` + `app.yaml` with `deployment.mode: installed` generates today's app byte-for-byte (no regression).
- The same inputs with `deployment.mode: deployed` generate a coherently different app per the dimensions above, `--check` in_sync.
- Switching the mode value changes drift state (FR-DET-1); switching it back restores in_sync (FR-DET-2).
- `startd8 wireframe` reports mode + posture.
- Incoherent mode/DSN combos fail the build with a clear message (FR-CFG-5).

---

## 7. Bucket Boundary (per CLAUDE.md)

This capability is **bucket 1 (applicational completion)**: it builds the structural skeleton for
*who can see what* and *where data lives* — deterministic, $0 LLM. It explicitly stops at the
mechanism. The **policy and content** that fill that skeleton — the company's chosen identity
provider, its password/retention rules, its real data — are **bucket 4**, provided by the
operator/commissioning company, not authored by the SDK. The determinism story ("~89% deterministic")
describes this skeleton, not the policy content.

---

## 8. Dimension Classification (generation-time vs runtime — added v0.2, FR-CFG-3)

Planning forced an explicit per-dimension classification. **Only one file's bytes vary by mode.**

| Dimension | Class | Mechanism |
|-----------|-------|-----------|
| Mode constant (`DEPLOYMENT_MODE`) | **Generation-time (a)** | `app/settings.py` — the single byte-varying, drift-hashed file (FR-CFG-7) |
| Auth seam (`app/auth.py`) | **Generation-time (a)** | emitted only in deployed; optional module via tolerant import (FR-IDN-2) |
| Tenant-scoped queries | **Generation-time (a) — Tier B** | routers/templates/tests (deferred, FR-TEN-*) |
| Persistence pool / pragmas | **Runtime (b)** | db.py reads settings; dialect branch already exists (FR-PER-2) |
| create_all gate | **Runtime (b)** | db.py `init_db()` reads mode; main.py frozen (FR-PER-3) |
| Bind host | **Runtime (b)** | run command / Dockerfile default; settings surfaces it (FR-NET-1) |
| Secrets backend default | **Runtime (b)** | existing `secrets/` switch; mode sets default (FR-SEC-1) |
| Observability posture | **Runtime (b)** | OTel env; mode sets default, orthogonal axis (FR-OBS-1) |

*v0.2 — Post-planning self-reflective update. 2 requirements narrowed (FR-PER-2, FR-IDN-2), 1
reclassified (FR-PER-3), 1 clarified (FR-NET-1), 3 deferred to Tier B (FR-TEN-1/2/3), 1 added
(FR-CFG-7), 7 open questions resolved (OQ-1..7). Ready for optional CRP review (Phase 5).*

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
