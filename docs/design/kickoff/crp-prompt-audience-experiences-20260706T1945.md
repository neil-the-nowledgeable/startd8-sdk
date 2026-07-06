# Convergent Review Prompt

**Generated:** 2026-07-06 19:45:25 UTC
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
| **Plan** | `/Users/neilyashinsky/Documents/dev/startd8-persona-exp/docs/design/kickoff/PERSONA_EXPERIENCES_PLAN.md` | 119 lines · 983 words |
| **Requirements** | `/Users/neilyashinsky/Documents/dev/startd8-persona-exp/docs/design/kickoff/PERSONA_EXPERIENCES_REQUIREMENTS.md` | 324 lines · 3372 words |
| **CRP guide** | `/Users/neilyashinsky/Documents/dev/startd8-sdk/docs/design/arc-review/CONVERGENT_REVIEW_AGENT_GUIDE.md` | 801 lines · 6412 words |
| **Review focus (sponsor)** | `/Users/neilyashinsky/Documents/dev/startd8-persona-exp/docs/design/kickoff/crp-focus-kickoff-persona-experiences.md` | 44 lines · 373 words |

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

# CRP Focus — Kickoff Persona Experiences

**Target (least-reviewed):** `PERSONA_EXPERIENCES_REQUIREMENTS.md` (v0.3) + `PERSONA_EXPERIENCES_PLAN.md` (v1.0)
**Both docs are brand-new** — no prior review rounds. Dual-document mode.

## Settled — do NOT relitigate

These were decided with the user or established by the planning pass. Reviewers should build on them,
not reopen them:

- **Persona is a lens over the ONE canonical experience** — not three parallel experiences, not a
  prose fork. (NR-1.)
- **Orthogonal to `posture`** (fluency axis ⟂ trust axis); no 3×2 matrix of experiences. (NR-3.)
- **Selection = explicit, project-remembered, changeable** — via the `guided` preference ladder
  (NOT posture, which the planning pass proved has no store). (FR-1.)
- **Scope = persona may pick different DEFAULTS**, reconciled to byte-identity: fills **unledgered**
  fields only, never overrides an explicit choice; same explicit decisions ⇒ byte-identical output;
  provenance-tagged. (FR-4/5/6.)
- **Default persona = Intermediate = today's walk, byte-identical.** (FR-2.)
- **Two-knob model** (DISCLOSURE × SURFACE); Beginner = expanded+reduced, Advanced = compact+full.
- **Naming SETTLED = `audience`** (both code AND user-facing CLI verb), resolving the
  `stakeholder_panel` "persona" ×319 overload (§0.1/§0.3, OQ-12). `persona` is reserved for the
  roster concept. **Do not relitigate the word**; the filename/title keep "Persona" as a cosmetic
  follow-up. Reviewers MAY verify terminology is applied *consistently*, but not reopen the choice.

## Where independent review is most valuable

- **FR-9 (disclosure without forking)** — the single NR-1 risk. Is the "same-doc delimiter-marked
  region" model actually sufficient, or does plain-language beginner prose diverge enough in
  structure that a projection can't hold? Is there a cleaner single-source mechanism?
- **FR-11 pre-pass (`apply_audience_defaults`)** — writing shielded defaults *before* a filtered walk.
  Any ordering/idempotency hazard vs. the existing confirm machinery? Interaction with OQ-10
  (persona-switch re-run).
- **OQ-8** — ledger provenance encoding (new `mode` value vs. additive `provenance` field) and
  backward-tolerance for existing `v1` ledgers on disk.
- **OQ-9** — which fields Beginner shields (domain- vs field-granular); the safety of silently
  writing them.
- **Byte-identity guarantee (FR-4)** — is a golden test sufficient, or does persona leak into output
  through any path the planning pass missed (e.g. ordering, timestamps, `at` fields in the ledger)?

## Known-thin areas (author-acknowledged)

- Web persona control scope (OQ-11) is deliberately deferred to M5.
- No persona **inference** in v1 (NR-2) — explicit only.

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-persona-exp/docs/design/kickoff/PERSONA_EXPERIENCES_PLAN.md`  ·  **Size:** 119 lines · 983 words

```markdown
# Kickoff Persona Experiences — Implementation Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-06
**Requirements:** `PERSONA_EXPERIENCES_REQUIREMENTS.md` (v0.2)

---

## Approach

Persona is a **lens** over the one canonical guided experience — a new dimension **orthogonal** to
`posture`. It resolves to two knobs (DISCLOSURE = prose tier; SURFACE = prompted vs. pre-written).
The build is sequenced so the **persistence spine ships first with zero behavior change**
(Intermediate == today, byte-identical), then each knob is layered behind it.

### New / touched modules

| Module | Change |
|--------|--------|
| `concierge/persona.py` *(new)* | `Persona` enum (`beginner\|intermediate\|advanced`); `resolve_audience_preference` (clone of `guided_routing.resolve_guided_preference`); `apply_audience_defaults` pre-pass; disclosure-tier map. |
| `kickoff_inputs/build_preferences.py` | Add `persona: Optional[str]` to `BuildPreferencesManifest` + validation. |
| `config.py` | Reuse global `preferences.persona` (existing `set_preference`/`get_preference` path, `:299-309`). |
| `kickoff_experience/manifest.py` | Add `AUDIENCE_PROFILES` data + `audience_defaults(persona, cfg)` accessor; `lint_config` coverage for profile value_paths. |
| `concierge/confirmation.py` | Bump `LEDGER_SCHEMA → v2`; add provenance to `ConfirmPlan`/ledger entry; add `audience_defaulted` bucket to `domain_confirmation`. |
| `concierge/confirm_walk.py` | One persona predicate in the `awaiting_fields` comprehension (`:70-73`); advanced prose suppression in `field_prompt_lines` (`:89-108`). |
| `concierge/writes.py` | `load_experience_doc(compact:bool) → tier:str`; new `<!-- PLAIN -->` regions in `KICKOFF_EXPERIENCE_INTRO.md`; update 4 callers. |
| `kickoff_experience/concierge_view.py` | audience block in `build_guided_view` (`:675`) + `guided_parity_digest` (`:719`). **NB path** — this file is under `kickoff_experience/`, not `concierge/`. |
| `cli_concierge.py` | New `kickoff audience [show\|set]` command; `--as-is` batch flag on `kickoff confirm` (FR-12). |
| `test_guided_experience_m4.py` | Update expected parity digests to carry `persona`. |

## Milestones

### M1 — Persistence spine (FR-1, FR-2, FR-3)
`persona.py` resolver + `BuildPreferencesManifest.persona` + global preference + `kickoff audience`
command. Resolver returns **Intermediate** on UNSET; the Intermediate path is today's
`awaiting_fields`/`build_guided_view` with no filter and no pre-pass. **Ships with zero behavior
change** — pure persistence + selection. Guards FR-4 by construction for unset users.

### M2 — Provenance + counting (FR-6, FR-13, OQ-5, OQ-8)
Ledger `v2` with a `audience-default:<slug>` provenance (encoding decided by OQ-8 — leaning additive
`provenance` field for backward tolerance); `domain_confirmation` gains the `audience_defaulted`
bucket; `assess` surfaces it. Pure ledger/reporting — testable in isolation, no UX change yet.

### M3 — Profiles + surface pre-pass (FR-5, FR-7, FR-8, FR-11; needs OQ-9)
`AUDIENCE_PROFILES` in `manifest.py`; `apply_audience_defaults` pre-pass writing shielded defaults via
existing `build_confirm_plan`/`apply_confirm`; persona predicate on `awaiting_fields`. Beginner
reduced-but-written surface goes live. **Blocked on OQ-9** (which fields are shielded — domain- vs
field-granular) before the profile shape is fixed.

### M4 — Disclosure tiers (FR-9, FR-10) — HIGHEST DRIFT RISK
Author `<!-- PLAIN -->` regions **inside** `KICKOFF_EXPERIENCE_INTRO.md`; migrate
`load_experience_doc` to `tier`; wire advanced suppression + beginner plain-language. **Gate on a
single-source review** — the one place NR-1 (no prose fork) can be violated. A separate plain-language
file is prohibited.

### M5 — Efficiency + parity (FR-4, FR-12, FR-14; needs OQ-11)
Advanced confirm-all `--as-is` batch; `persona` block in guided view + parity digest; byte-identity
golden test across personas for a fixed decision script. Update `test_guided_experience_m4.py`.
OQ-11 decides whether web gets a persona *selector* or only *renders* the preference.

## Sequencing rationale

- M1 first so everything downstream has a resolved persona to key on, with **no user-visible change**
  until a knob lands — de-risks the whole feature (can ship M1 and stop).
- M2 before M3 because the pre-pass (M3) must write the provenance the ledger only understands after
  M2 — otherwise audience-defaults masquerade as human confirmations.
- M4 isolated and gated because it is the sole NR-1 (single-source) risk.
- M5 last: parity + byte-identity golden is the acceptance gate proving persona stayed a lens.

## Test strategy

- **Byte-identity golden (FR-4):** a fixed explicit-decision script produces identical `inputs/` +
  `confirmed.yaml` *values* under all three personas.
- **Provenance round-trip (FR-6/FR-13):** audience-default → `domain_confirmation` reports
  `audience_defaulted`; `kickoff confirm <vp>` promotes it to `explicit`.
- **Pre-pass no-override (FR-5):** a field explicitly set before the pre-pass is left untouched.
- **Parity digest (FR-14):** CLI == web == TUI persona rendering (extend existing M4 parity test).
- **Single-source disclosure (FR-9):** loader `tier` projection reads one doc; a lint/test asserts no
  second plain-language file exists.

## Open dependencies (from requirements §5)

- **OQ-8** (ledger provenance encoding) gates M2.
- **OQ-9** (which fields Beginner shields) gates M3 profile shape.
- **OQ-10** (persona-switch re-runs pre-pass?) gates M1/M3 boundary behavior.
- **OQ-11** (web persona selector vs render-only) gates M5 scope.

---

*v1.0 — mapped from requirements v0.2. Five milestones; M1 ships zero-behavior-change persistence,
M4 is the single drift-risk gate. Four open questions block specific milestones.*

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

**Path:** `/Users/neilyashinsky/Documents/dev/startd8-persona-exp/docs/design/kickoff/PERSONA_EXPERIENCES_REQUIREMENTS.md`  ·  **Size:** 324 lines · 3372 words

```markdown
# Kickoff Persona Experiences — Requirements

**Version:** 0.5 (Audience naming resolved; panel findings folded)
**Date:** 2026-07-06
**Status:** Draft
**Owners:** kickoff kernel (`concierge/`, `kickoff_experience/`)
**Related:** `ADR_RETIRE_RED_CARPET_WIZARD.md`, `KICKOFF_UX_v0.5`, value-input-confirmation, content-contract
**Plan:** `PERSONA_EXPERIENCES_PLAN.md`

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2 (post-planning). The
> planning pass touched the real seams and falsified the draft's central persistence assumption plus
> three more — a >30% revision, i.e. the loop working as intended.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-1: persona is "stored the way `posture` is stored." | **`posture` is NOT persisted** — it's a per-invocation flag defaulting to `"prototype"` (`writes.py:168`, `cli_concierge.py:317`, `web.py:962`). The guided "current_mode" reads `deployment.mode` from `app.yaml`, a different field; the flow explicitly never records a posture choice (`concierge_view.py:666`). | FR-1 retargeted: persona mirrors the **`guided` preference ladder** (project `build-preferences.yaml` → global `~/.startd8/config.json` → default), which is the *real* persisted, changeable per-project preference (`guided_routing.py:113`, `build_preferences.py:44`, `config.py:299`). |
| FR-6: extend `FieldDef.provenance_default`. | Two provenance concepts. `FieldDef.provenance_default` is a static template fact in a **closed** set `{authored, estimate, config-default, templated}` (`manifest.py:38`). Per-decision provenance lives in the **ledger** `confirmed.yaml` as `{value, at, mode}`, `mode ∈ {set, as-is}` (`confirmation.py:37`). | `audience-default:<slug>` is a **ledger** provenance, not a `FieldDef` value. FR-6 extends the ledger schema (bump `kickoff.confirmed.v1 → v2`), never the closed `PROVENANCE_DEFAULTS` set. |
| FR-11: the walk can "skip fields while writing them." | The walk **skips by NOT writing** — Enter appends to `skipped[]` and moves on; nothing persists (`confirm_walk.py:141`). "Skip-but-write" is not a walk behavior. | FR-11 retargeted to a **pre-pass** (`apply_audience_defaults`) that writes persona defaults via the existing `build_confirm_plan`/`apply_confirm` *before* the walk; ledgered fields are then auto-dropped by the unchanged `awaiting_fields`. The walk loop is untouched. |
| FR-9: `compact` generalizes to 3 tiers. | `compact` is a **binary** HTML-comment slice (`<!-- TL;DR -->…`, `writes.py:126`). No third region; beginner plain-language prose exists nowhere. | FR-9 is single-source-safe **only** if the expanded tier is authored as **additional delimiter-marked regions inside the same doc** (`<!-- PLAIN -->…`), turning the loader from a `bool` into a 3-value `tier` projection. A separate file would fork prose (violates NR-1). Now mandated explicitly. |
| OQ-6: `KickoffState` may need a `persona` field. | `KickoffState.to_dict` is the **extraction** payload, orthogonal to the guided experience. The real cross-surface contract is `build_guided_view` + `guided_parity_digest`, enforced byte-equal across CLI/web/TUI by `test_guided_experience_m4.py:155`. | Persona goes in the **guided view-model + parity digest**, never `KickoffState`. The existing parity test does not break — it *enforces* FR-14 (all surfaces render persona in lockstep). |
| FR-5: "never override explicit." | The ledger already records explicit decisions and `awaiting_fields` already excludes ledgered fields (`confirm_walk.py:69`). | FR-5 is **nearly free**: a pre-pass that only touches unledgered fields inherits the guarantee. |

**Resolved open questions:**
- **OQ-1 → posture has NO store.** Persona rides the `guided` preference ladder instead (see FR-1).
- **OQ-2 → ledger, not FieldDef.** `audience-default:<slug>` extends the ledger entry; bump schema to v2.
- **OQ-3 → delimiter-region model required.** Feasible only as marked regions in the same doc (FR-9).
- **OQ-4 → filter is trivial, but writing needs a pre-pass.** `awaiting_fields` gains one predicate; a new `apply_audience_defaults` does the writing (FR-11).
- **OQ-5 → new `audience_defaulted` count bucket.** Otherwise audience-defaults masquerade as human-confirmed in `domain_confirmation` (FR-13).
- **OQ-6 → guided view-model + parity digest, not `KickoffState`.** (FR-14.)
- **OQ-7 → `manifest.py` config layer.** Profiles are in-process data (`AUDIENCE_PROFILES`), not packaged/downloaded files.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK lessons (phantom-reference audit, overloaded-term co-location, single-source
> vocabulary ownership, CRP steering) before external review. Two changed the draft materially:

- **[Phantom-reference audit]** — grepped every existing symbol the spec leans on. All verified
  (`resolve_guided_preference` `guided_routing.py:113`, `BuildPreferencesManifest`
  `kickoff_inputs/build_preferences.py:28`, `PROVENANCE_DEFAULTS` `manifest.py:38`, `LEDGER_SCHEMA`
  `confirmation.py:33`, `domain_confirmation` `confirmation.py:150`, `load_experience_doc`
  `writes.py:130`, `get/set_preference` `config.py:299/303`) **except a path error**: the FR-14
  anchors `build_guided_view` / `guided_parity_digest` live in
  **`kickoff_experience/concierge_view.py`** (`:675` / `:719`), not `concierge/concierge_view.py`.
  Corrected in the plan. New symbols (`resolve_audience_preference`, `apply_audience_defaults`,
  `AUDIENCE_PROFILES`) are to-be-created and marked as such.
- **[Overloaded-term co-location] — MATERIAL.** "persona" is **already an owned term** in this
  codebase (**319 occurrences**): in `stakeholder_panel/`, `requirements_panel/`, `persona_drafting`,
  `cli_panel.py`, a *persona* is a **synthetic stakeholder/reviewer voice queried from a roster**.
  This feature's "persona" (the human user's software-fluency archetype) is a **second, unrelated
  meaning**. Per the lesson, the new concept must **not** co-locate under the same bare identifier —
  a `concierge/persona.py` beside `persona_drafting` would actively mislead. **Hardening applied:**
  all symbols for this feature are namespaced to a distinct term (**`audience`** — `KickoffAudience`
  enum, `audience.py`, `AUDIENCE_PROFILES`, `resolve_audience`), reserving "persona" for the existing
  roster concept. **RESOLVED (OQ-12): the user-facing label is also `audience`** — `startd8 kickoff
  audience` — so code and CLI share one collision-free term. (The prose in §0.1/§0.2/OQ-12 still says
  "persona" *where it denotes the stakeholder-panel roster concept under discussion*; see the
  terminology banner below §0.2.)
- **[Single-source vocabulary ownership]** — this doc is the **owner** of the audience/fluency model
  and the two-knob (disclosure × surface) vocabulary; it *cites* (does not restate) the
  content-contract single-source rule and the `posture` axis, which are owned elsewhere. No drift
  introduced.
- **[CRP steering]** — both docs are brand-new (least-reviewed). The CRP target is
  `PERSONA_EXPERIENCES_REQUIREMENTS.md`; settled/do-not-relitigate items (the 3 user decisions,
  persona-as-lens, orthogonality-to-posture, byte-identity guardrail) are carried in
  `crp-focus-kickoff-persona-experiences.md`.

### 0.2 Panel Dogfood Findings (v0.4)

> **Recursive dogfood:** we ran the SDK's own adversarial stakeholder panel
> (`startd8 kickoff panel ask-all`, Sonnet) with a roster of the **three proposed audiences embodied
> as end-users** (`docs/kickoff/inputs/stakeholders.yaml`). Each critiqued this very doc from its
> lived perspective. Findings are SYNTHETIC/UNRATIFIED (the tool flags them so) but several were
> clearly correct and are folded in below. Full transcript persisted to `.startd8/transcripts/`.

| Finding | Audience | Resolution |
|---------|----------|-----------|
| No requirement for the beginner "we filled some things in — here's where to change them" moment | Beginner | **New FR-15** |
| No in-session "show me everything now" escape hatch (undo the pre-pass mid-session) | Beginner | **New FR-16** |
| `audience_defaulted` bucket silently changes the `assess` display even for unset/Intermediate users | Intermediate | **FR-13 fix** (display byte-identity when no audience defaults exist) |
| Provenance shown in ledger/assess but not LIVE in the walk where decisions are made | Intermediate | **New FR-17** |
| FR-2/FR-4 byte-identity asserted, not demonstrated — name the test + merge gate | Int + Adv | **FR-4 sharpened** |
| Confirm-all is a blind batch write — needs a dry-run / pre-commit diff | Advanced | **New FR-18** |
| OQ-12 mis-prioritized: collision is a correctness decision, not a warmth call | Advanced | **Resolved → user chose user-facing `audience`** (the veteran archetype's objection won) |

### 0.3 Canonical terminology (read before reviewing)

> **CANONICAL TERM: `audience`.** The user-facing CLI verb (`startd8 kickoff audience`) and **all**
> code symbols (`KickoffAudience`, `audience.py`, `AUDIENCE_PROFILES`, `resolve_audience`,
> `apply_audience_defaults`, `audience_defaulted`, `audience-default:<slug>`) use `audience`. This
> resolves the ×319 "persona" overload (OQ-12) — **`persona` is reserved for the `stakeholder_panel`
> roster concept.** The word "persona" still appears in this doc **only** in §0.1/§0.2 and OQ-12,
> where it deliberately denotes that roster concept under discussion. The **filename/title retain
> "Persona"** for git/reference continuity; a cosmetic file rename is a tracked follow-up, not a
> blocker.

---

## 1. Problem Statement

The `startd8 kickoff` experience was distilled from overlapping tools (welcome-mat, red-carpet)
into **one** kernel + **one** guided experience, with a hard-won **render-only, single-source**
content contract (no prose forks) and a **SOTTO byte-identity** guarantee.

The one guided experience is calibrated for a single implicit user: someone *familiar with
software*. It over-explains for a veteran (prose is noise; they want the field list and to edit
everything) and under-scaffolds for a newcomer (unfamiliar vocabulary — "observability",
"conventions", "schema contract" — presented as decisions they can't meaningfully make).

We want **persona-tailored** project-start experiences for three archetypes:

| Persona | Archetype | Needs |
|---------|-----------|-------|
| **Beginner** | new to software | plain-language framing, shielded from decisions they can't make, strong safe defaults, reassurance/reversibility |
| **Intermediate** | familiar with software | today's guided walk — all domains, light "why", pre-filled defaults |
| **Advanced** | software veteran | terse, full decision surface, all defaults visible & editable, confirm-all efficiency, prose suppressed |

### Gap table

| Component | Current State | Gap |
|-----------|--------------|-----|
| Experience selection | Only `posture` (prototype/production), a *trust/authority* axis — **and not even persisted** (per-invocation flag) | No *fluency* axis; one-size guided walk |
| Preference persistence | The `guided` tri-state ladder DOES persist a per-project changeable preference (`build-preferences.yaml` → global config → default) | No `persona` field on that ladder |
| Prose density | Single binary `compact` slice in `load_experience_doc` | No 3-tier projection; no plain-language region authored |
| Decision surface | All 4 input domains always exposed by `awaiting_fields` | No persona filter; no write-the-shielded pre-pass |
| Decision provenance | Ledger records `{value, at, mode ∈ set|as-is}` | No `audience-default:<slug>` provenance; `domain_confirmation` can't distinguish it |

## 2. Design Model (normative framing)

Persona is a **lens over the ONE canonical experience**, never three parallel experiences. Same 4
input domains, same fields, same `confirmed.yaml` ledger. Persona is **orthogonal** to `posture`
(fluency axis ⟂ trust axis); we do **not** build a 3×2 matrix of experiences.

Persona resolves to **two orthogonal knobs**:

- **DISCLOSURE** — prose density, projected from a single source at 3 tiers (compact / light / expanded).
- **SURFACE** — how many decisions are *exposed for prompting* vs. *silently sound-defaulted-and-written*.

| Persona | Disclosure tier | Surface |
|---------|-----------------|---------|
| Beginner | `expanded` (plain-language) | Reduced (pre-pass writes shielded defaults; walk prompts the remainder) |
| Intermediate | `light` (today's walk) | Full, pre-filled — **byte-identical to today** |
| Advanced | `compact` (per-field prose suppressed) | Full, all defaults visible + confirm-all |

**Key non-obvious point:** Beginner is *not* the opposite of Advanced. Beginner = expanded prose +
*reduced* surface; Advanced = compact prose + *full* surface. Different corners of a 2×2, not two
ends of one slider.

## 3. Requirements

### Selection & persistence
- **FR-1** *(revised — D-1)* Persona is an explicit, project-remembered, changeable selection that
  rides the **existing `guided` preference ladder**: resolved flag → project `build-preferences.yaml`
  `persona:` → global `~/.startd8/config.json` `preferences.persona` → default. It does **not**
  mirror `posture` (which has no store). Add a `persona` field to `BuildPreferencesManifest` and a
  `resolve_audience_preference` clone of `resolve_guided_preference`.
- **FR-2** Default persona (when unset) is **Intermediate** — today's guided walk — so existing
  behavior is byte-identical for anyone who never picks a persona.
- **FR-3** A user can view and change the current persona (`kickoff audience [show | set <slug>]`),
  writing the project and/or global preference exactly as the `guided` preference is written.

### Byte-identity / provenance guardrail
- **FR-4** *(sharpened — panel I1/A2)* Persona is a **presentation + default-selection** projection
  only. Given the **same explicit decisions**, output (`inputs/`, `confirmed.yaml` values) is
  **byte-identical** across personas. This is not merely asserted: a **named golden test**
  (`test_audience_byte_identity`) drives a fixed explicit-decision script under all three audiences
  and asserts identical output, and the M5 acceptance gate **blocks merge if that test is absent or
  failing**. (Property emerges from FR-5 + FR-9; the test is the proof the reviewer can point at.)
- **FR-5** *(nearly free — D-7)* Persona-chosen defaults fill **unledgered** fields only; the
  pre-pass skips any `value_path` already in `confirmed_value_paths`, so persona **never overrides an
  explicit choice**.
- **FR-6** *(revised — D-3)* Every persona-written value carries **ledger** provenance distinguishing
  it from an explicit confirmation: extend the ledger entry (`confirmed.yaml`) with a
  `audience-default:<slug>` provenance and bump `LEDGER_SCHEMA` to `kickoff.confirmed.v2`
  (backward-tolerant load). The closed `FieldDef.PROVENANCE_DEFAULTS` set is **not** touched.

### Per-persona default profiles
- **FR-7** *(sited — OQ-7)* Each persona has a **default profile** in the `manifest.py` config layer
  (`AUDIENCE_PROFILES: dict[slug, dict[value_path, value]]`) — a single-source, in-process
  field→value table consulted when a field is unledgered. Not a packaged/downloaded file.
- **FR-8** Default profiles are **partial**: a persona specifies only the fields where it differs
  from the base; unspecified fields inherit the base `FieldDef` default behavior. `lint_config`
  gains a check that every profile `value_path` exists in the config.

### Disclosure knob
- **FR-9** *(revised — D-5, drift trap)* The content loader surfaces prose at the persona's
  disclosure tier via a **single-source projection**: change `load_experience_doc(key, *,
  compact: bool)` to `tier ∈ {compact, light, expanded}`, where the `expanded` (plain-language)
  content is authored as **additional delimiter-marked regions inside the same doc**
  (`<!-- PLAIN -->…<!-- /PLAIN -->`). Authoring the expanded tier in a **separate file is
  prohibited** (would fork prose, violating NR-1).
- **FR-10** Beginner disclosure renders plain-language framing for domain "why"/"what"; Advanced
  suppresses per-field `why`/`grammar` lines in `field_prompt_lines`.

### Surface knob
- **FR-11** *(revised — D-4)* Beginner **reduces** the prompted surface via a **pre-pass**
  (`apply_audience_defaults`) that, for each reduced-surface field not yet in the ledger, writes the
  persona default through the existing `build_confirm_plan` + `apply_confirm` machinery (tagged
  `audience-default:<slug>`). The written fields then drop out of the **unchanged** `awaiting_fields`;
  the walk prompts only the remainder. Shielded decisions are **written, never omitted** (never a
  reduced contract).
- **FR-12** *(scoped — batch of existing as-is)* Advanced exposes the **full** surface with a
  **confirm-all** path: a batch loop over `awaiting_fields` calling `build_confirm_plan(mode="as-is")`
  + `apply_confirm` for each (reuses the single-field `--as-is` machinery that already exists). Gated
  by the FR-18 pre-commit preview. **(sharpened — panel A2)** A **named test**
  (`test_confirm_all_equals_single`) MUST assert the batch path produces **byte-identical ledger
  entries** to N single-field `--as-is` confirmations — proving "reuses" is not a second code path
  that can drift.
- **FR-13** *(revised — OQ-5)* An audience-defaulted field must be **distinguishable from a human
  confirmation** so a beginner can later reach shielded decisions: `domain_confirmation` gains an
  `audience_defaulted` bucket (routed by the FR-6 provenance) instead of counting them as
  `confirmed`; `assess` surfaces it; `kickoff confirm <vp>` re-writes an audience-default into an
  `explicit` confirmation. **(fix — panel I2)** When **no** audience-default entries exist on disk
  (the unset/Intermediate case), `domain_confirmation`/`assess` output is **byte-identical to today**
  — the new bucket is empty/omitted, so users who never touch audience see **no display regression**.
  (Extends FR-2/FR-4 byte-identity to the reporting surface.)

### Panel-derived (v0.4 — from the audience dogfood)
- **FR-15** *(Beginner B2)* When the pre-pass (FR-11) writes shielded defaults, the reduced-surface
  experience MUST surface a **plain-language reassurance moment**: "we filled in N things for you —
  here's where to see and change them." The mechanism (FR-6/FR-13) is not enough; the *user-facing
  communication* is itself a requirement.
- **FR-16** *(Beginner B4)* A user MUST have an **in-session escape hatch to expand the surface now**
  ("show me everything") — reversing the reduced-surface shielding for the current session, distinct
  from changing the audience preference for the *next* session (FR-3). Reversal converts
  audience-default fields back to `awaiting` (or re-prompts them); it never clobbers an `explicit`
  value (FR-5).
- **FR-17** *(Intermediate I4)* The confirm **walk itself** — not only `assess` after the fact — MUST
  render a **live per-value provenance indicator** distinguishing an audience-defaulted value from
  one the user explicitly accepted, at the prompt where the decision is made. (Ledger provenance FR-6
  is the data; this is its surfacing at the point of decision.)
- **FR-18** *(Advanced A4)* The Advanced **confirm-all** path (FR-12) MUST offer a **pre-commit
  preview / `--dry-run`**: show the full field→value table that will be batch-written and require a
  single explicit confirmation before `apply_confirm` runs. A blind bulk sweep over `awaiting_fields`
  is prohibited — it is indistinguishable from the tool making choices for the user.

### Surface parity (CLI / TUI / web)
- **FR-14** *(sited — OQ-6)* Persona applies identically across CLI, TUI, and web by adding a
  `persona` block to `build_guided_view` and a `persona` key to `guided_parity_digest`
  (alongside the existing `posture` block). The existing byte-equal parity test enforces lockstep;
  `KickoffState` is **not** touched.

## 4. Non-Requirements

- **NR-1** No three parallel experiences / no prose forks. Persona is a lens; the expanded
  disclosure tier MUST be same-doc marked regions (FR-9), not a second file.
- **NR-2** No automatic persona **inference** from git/code signals in v1 (explicit selection only).
- **NR-3** Persona does **not** replace or subsume `posture`; the two remain orthogonal.
- **NR-4** No new input domains, no `.prisma`/contract change, no change to what an app *is* — only
  the path to the same kickoff inputs.
- **NR-5** No persona-specific *widgets* or wholly new UI components in v1 (reuse the confirm-walk
  and existing surfaces).
- **NR-6** *(new)* No change to `KickoffState.to_dict` (the extraction payload) — persona lives only
  in the guided view-model.

## 5. Open Questions (post-planning)

- **OQ-8** Provenance encoding in the ledger entry: a **new `mode` value** (`mode: "audience-default"`
  plus a `persona:` key) vs. an **additive `provenance` field** on the existing entry. Which is more
  backward-tolerant for existing `v1` ledgers on disk? (Leaning additive `provenance` field.)
- **OQ-9** For Beginner reduced surface, *which specific fields/domains* are shielded? Is it
  domain-granular (e.g. shield all of `observability` + `conventions`) or field-granular? (Affects
  the `AUDIENCE_PROFILES` shape and the `awaiting_fields` predicate.)
- **OQ-10** Should `kickoff audience set` re-run the pre-pass immediately (apply beginner defaults on
  switch) or only affect the *next* guided invocation? (Idempotency + surprise-write concern.)
- **OQ-11** Does the web surface need a persona selector control in v1, or is persona set via
  CLI/preference and merely *rendered* by web? (Scope of the M5 parity work.)
- **OQ-12 → RESOLVED (user, post-panel).** **User-facing label = `audience`** (`startd8 kickoff
  audience`), matching the code namespace — one collision-free term for both surfaces. The panel
  dogfood elevated this from a warmth call to a correctness decision: the **veteran archetype** — the
  person most likely to use both this and the `stakeholder_panel` `persona` roster commands — argued
  that keeping user-facing "persona" would confuse in help text. The user accepted that argument over
  the earlier "keep persona" preference. See §0.3 for the canonical-terminology rule.

---

*v0.3 — Post lessons-learned hardening. Applied 4 lessons: phantom-reference audit (caught a
`concierge/` vs `kickoff_experience/` path error on the FR-14 anchors), overloaded-term co-location
(MATERIAL — "persona" is an owned term ×319; code namespaced to `audience`, OQ-12 raised for the
surface word), single-source vocabulary ownership (clean), CRP steering (target + focus file named).*

*v0.4 — Post persona-panel dogfood. Ran the SDK's own adversarial stakeholder panel with the three
proposed personas embodied as end-users, reviewing this doc. Folded in FR-15 (beginner reassurance
moment), FR-16 (in-session surface-expand escape hatch), FR-17 (live provenance in the walk), FR-18
(confirm-all dry-run); sharpened FR-4/FR-12 to name their guardrail tests; fixed FR-13 (no display
regression for non-audience users); elevated OQ-12 (the veteran archetype argues against the "keep
persona" default — needs a user decision).*

*v0.5 — OQ-12 RESOLVED by the user: user-facing label = `audience` (the veteran archetype's
correctness objection won over the earlier "keep persona" steer). Renamed all code-symbol tokens
persona→audience for one collision-free term; added §0.3 canonical-terminology banner; `persona`
now denotes ONLY the `stakeholder_panel` roster concept (in §0.1/§0.2/OQ-12). Filename/title retain
"Persona" pending a cosmetic follow-up rename. Ready for CRP review.*

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
